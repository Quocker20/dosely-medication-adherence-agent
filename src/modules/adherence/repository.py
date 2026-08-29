import logging
import uuid
from datetime import datetime, timedelta, timezone as dt_timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import Exists, case, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.sql.elements import ColumnElement

from src.modules.adherence.models import (
    AdherenceLog,
    Alert,
    HealthSurvey,
    NotificationDelivery,
    NotificationDoseItem,
    SymptomReport,
)
from src.modules.agents.models import ScheduledDose
from src.modules.auth.models import UserDevice
from src.modules.patients.models import CaregiverLink, PatientProfile
from src.modules.prescriptions.models import Prescription, PrescriptionItem

logger = logging.getLogger(__name__)


def _access_filter(actor_id: uuid.UUID, patient_id_col: ColumnElement):
    """Role-agnostic access predicate, duplicated per structure.md's
    vertical-slice isolation rather than imported — mirrors
    PrescriptionRepository._access_filter / ScheduledDoseRepository._access_filter:
    self-owned, doctor-prescribed, or active-caregiver-linked are independent
    facts checked together."""

    def _has_prescribed_filter() -> Exists:
        return (
            select(Prescription.id)
            .where(
                Prescription.doctor_id == actor_id,
                Prescription.patient_id == patient_id_col,
            )
            .exists()
        )

    def _has_active_caregiver_filter() -> Exists:
        return (
            select(CaregiverLink.id)
            .where(
                CaregiverLink.caregiver_user_id == actor_id,
                CaregiverLink.patient_id == patient_id_col,
                CaregiverLink.status == "ACTIVE",
            )
            .exists()
        )

    return or_(
        patient_id_col == actor_id,
        _has_prescribed_filter(),
        _has_active_caregiver_filter(),
    )


class AdherenceLogRepository:
    """Repository handling dose-action logging (AdherenceLog) and the
    ScheduledDose status transitions those actions drive."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get_patient_timezone_scoped(
        self, patient_id: uuid.UUID, actor_id: uuid.UUID
    ) -> Optional[str]:
        """Fetch a patient's timezone, access-scoped the same way as the
        adherence queries themselves — never leak timezone to a caller who
        couldn't read adherence data anyway. None means not found OR no
        access (indistinguishable, blocks UUID probing). Mirrors
        ScheduledDoseRepository.get_patient_timezone_scoped."""
        stmt = select(PatientProfile.timezone).where(
            PatientProfile.user_id == patient_id,
            _access_filter(actor_id, PatientProfile.user_id),
        )
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def apply_dose_action_cas(
        self,
        dose_id: uuid.UUID,
        patient_id: uuid.UUID,
        action: str,
        snooze_minutes: Optional[int] = None,
    ) -> Optional[ScheduledDose]:
        """Atomic compare-and-swap: only updates a row still PENDING, due
        now, and owned by this patient — no read-then-write race window
        (mirrors PrescriptionRepository.approve_if_draft). Returns None if
        the dose doesn't exist, isn't this patient's, is not due yet, or is
        no longer PENDING; caller (service) disambiguates via get_dose_scoped.

        TAKEN/SKIPPED move the dose to a terminal state. SNOOZE stays PENDING
        and only shifts current_scheduled_at / bumps snooze_count — computed
        as a column-relative expression (current_scheduled_at + interval,
        snooze_count + 1) so no prior SELECT of the current value is needed.
        """
        if action == "TAKEN":
            values: Dict[str, Any] = {"status": "TAKEN", "taken_at": func.now()}
        elif action == "SKIPPED":
            values = {"status": "SKIPPED"}
        elif action == "SNOOZE":
            values = {
                "current_scheduled_at": ScheduledDose.current_scheduled_at
                + timedelta(minutes=snooze_minutes or 0),
                "snooze_count": ScheduledDose.snooze_count + 1,
            }
        else:
            raise ValueError(f"Unsupported dose action: {action}")

        stmt = (
            update(ScheduledDose)
            .where(
                ScheduledDose.id == dose_id,
                ScheduledDose.patient_id == patient_id,
                ScheduledDose.status == "PENDING",
                # This is a clinical-boundary check, so it must stay in the
                # atomic UPDATE rather than relying on either client clocks
                # or a read-then-write service-layer comparison.
                ScheduledDose.current_scheduled_at <= func.now(),
            )
            .values(**values)
            .returning(ScheduledDose)
        )
        result = await self._db.execute(stmt)
        dose = result.scalar_one_or_none()
        if action == "SNOOZE" and dose is not None and dose.notification_group_id is not None:
            # Both statements run inside AdherenceService's transaction. Other
            # transactions therefore observe either the intact old group or
            # the snoozed dose with the whole group dissolved, never a mixed
            # state that could deliver the snoozed dose early.
            await self._db.execute(
                update(ScheduledDose)
                .where(ScheduledDose.notification_group_id == dose.notification_group_id)
                .values(notification_group_id=None)
            )
        return dose

    async def get_dose_scoped(
        self, dose_id: uuid.UUID, patient_id: uuid.UUID
    ) -> Optional[ScheduledDose]:
        """Fetch a dose scoped to its owning patient — used only to
        disambiguate why apply_dose_action_cas matched no row (not
        found/not owned vs. already actioned)."""
        stmt = select(ScheduledDose).where(
            ScheduledDose.id == dose_id, ScheduledDose.patient_id == patient_id
        )
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_doses_scoped(
        self, dose_ids: List[uuid.UUID], patient_id: uuid.UUID
    ) -> List[ScheduledDose]:
        """Fetch multiple doses scoped to their owning patient."""
        if not dose_ids:
            return []
        stmt = select(ScheduledDose).where(
            ScheduledDose.id.in_(dose_ids), ScheduledDose.patient_id == patient_id
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def get_next_dose_and_min_gap(
        self, dose: ScheduledDose, patient_id: uuid.UUID
    ) -> Tuple[Optional[ScheduledDose], Optional[int]]:
        """Fetch the next pending dose for the same prescription item and the item's minimum_interval_minutes."""
        stmt = (
            select(ScheduledDose, PrescriptionItem.minimum_interval_minutes)
            .join(PrescriptionItem, ScheduledDose.prescription_item_id == PrescriptionItem.id)
            .where(
                ScheduledDose.prescription_item_id == dose.prescription_item_id,
                ScheduledDose.patient_id == patient_id,
                ScheduledDose.status == "PENDING",
                ScheduledDose.id != dose.id,
                ScheduledDose.current_scheduled_at > dose.current_scheduled_at,
            )
            .order_by(ScheduledDose.current_scheduled_at.asc())
            .limit(1)
        )
        result = await self._db.execute(stmt)
        row = result.first()
        if row:
            return row[0], row[1]
        return None, None

    async def batch_apply_dose_actions_cas(
        self,
        dose_ids: List[uuid.UUID],
        patient_id: uuid.UUID,
        action: str,
        snooze_minutes: Optional[int] = None,
    ) -> List[ScheduledDose]:
        """Atomic batch CAS update for multiple doses: updates all rows matching
        dose_ids that are still PENDING and owned by this patient.
        Returns the list of updated ScheduledDose rows."""
        if not dose_ids:
            return []

        if action == "TAKEN":
            values: Dict[str, Any] = {"status": "TAKEN", "taken_at": func.now()}
        elif action == "SKIPPED":
            values = {"status": "SKIPPED"}
        elif action == "SNOOZE":
            values = {
                "current_scheduled_at": ScheduledDose.current_scheduled_at
                + timedelta(minutes=snooze_minutes or 0),
                "snooze_count": ScheduledDose.snooze_count + 1,
            }
        else:
            raise ValueError(f"Unsupported dose action: {action}")

        stmt = (
            update(ScheduledDose)
            .where(
                ScheduledDose.id.in_(dose_ids),
                ScheduledDose.patient_id == patient_id,
                ScheduledDose.status == "PENDING",
            )
            .values(**values)
            .returning(ScheduledDose)
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def insert_log(
        self,
        patient_id: uuid.UUID,
        action: str,
        action_source: str,
        payload: Dict[str, Any],
        idempotency_key: str,
        scheduled_dose_id: Optional[uuid.UUID] = None,
    ) -> AdherenceLog:
        """Append-only insert. A duplicate idempotency_key raises
        IntegrityError (uq on the column) — caller catches it and treats the
        request as an idempotent replay."""
        log = AdherenceLog(
            scheduled_dose_id=scheduled_dose_id,
            patient_id=patient_id,
            action=action,
            action_source=action_source,
            payload=payload,
            idempotency_key=idempotency_key,
        )
        self._db.add(log)
        await self._db.flush()
        return log

    async def insert_batch_logs(
        self,
        patient_id: uuid.UUID,
        action: str,
        action_source: str,
        payload: Dict[str, Any],
        idempotency_key: str,
        scheduled_dose_ids: List[uuid.UUID],
    ) -> List[AdherenceLog]:
        """Insert adherence logs for multiple doses under a single batch request.
        Suffixes the idempotency_key per dose (e.g. key:dose_id) to respect
        unique constraint while guaranteeing idempotency."""
        logs: List[AdherenceLog] = []
        for dose_id in scheduled_dose_ids:
            key = f"{idempotency_key}:{dose_id}"
            log = AdherenceLog(
                scheduled_dose_id=dose_id,
                patient_id=patient_id,
                action=action,
                action_source=action_source,
                payload=payload,
                idempotency_key=key,
            )
            self._db.add(log)
            logs.append(log)
        await self._db.flush()
        return logs

    async def get_log_by_idempotency_key(self, idempotency_key: str) -> Optional[AdherenceLog]:
        stmt = select(AdherenceLog).where(AdherenceLog.idempotency_key == idempotency_key)
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_batch_logs_by_idempotency_key(
        self, idempotency_key: str
    ) -> List[AdherenceLog]:
        """Fetch all adherence logs matching idempotency_key prefix."""
        escaped_key = (
            idempotency_key.replace("\\", "\\\\")
            .replace("%", "\\%")
            .replace("_", "\\_")
        )
        prefix = f"{escaped_key}:%"
        stmt = (
            select(AdherenceLog)
            .where(
                or_(
                    AdherenceLog.idempotency_key == idempotency_key,
                    AdherenceLog.idempotency_key.like(prefix, escape="\\"),
                )
            )
            .order_by(AdherenceLog.created_at.asc())
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def get_dose_status_counts(
        self,
        patient_id: uuid.UUID,
        actor_id: uuid.UUID,
        range_start: datetime,
        range_end: datetime,
        overdue_minutes: int,
    ) -> Tuple[int, int, int, int]:
        """Single aggregate query (one round trip, FILTER-based conditional
        counts) returning (total, taken, skipped, missed) doses scheduled in
        [range_start, range_end) — avoids running four separate COUNT
        queries. Rides idx_scheduled_doses_patient_time (patient_id,
        current_scheduled_at).

        Only *due* doses count. A dose still PENDING within `overdue_minutes`
        of its scheduled time has had no chance to be actioned yet, so
        including it would deflate the rate for a patient who has done
        nothing wrong — the denominator must be doses that resolved or should
        have, not every dose on the calendar. `overdue_minutes` is the
        caller's settings.missed_dose_overdue_minutes, the same threshold
        MissedDoseScanService uses to flip PENDING -> MISSED, so the two
        agree on what "overdue" means.

        An overdue-but-still-PENDING dose is counted as missed rather than
        left in a fourth bucket: the scan is up to
        missed_dose_scan_interval_minutes behind, and without this the four
        returned figures would not sum to `total` and the client's summary
        card would show unexplained arithmetic. It also makes the result
        immune to racing the scan — under either snapshot the row lands in
        `missed`.

        The cutoff is evaluated SQL-side: Postgres now() is transaction start
        time, so the WHERE clause and every FILTER below see one instant with
        no skew between numerator and denominator.
        """
        overdue_cutoff = func.now() - timedelta(minutes=overdue_minutes)
        is_due = or_(
            ScheduledDose.status != "PENDING",
            ScheduledDose.current_scheduled_at <= overdue_cutoff,
        )
        stmt = select(
            func.count(ScheduledDose.id),
            func.count(ScheduledDose.id).filter(ScheduledDose.status == "TAKEN"),
            func.count(ScheduledDose.id).filter(ScheduledDose.status == "SKIPPED"),
            # No cutoff repeated here: the WHERE below already dropped every
            # not-yet-due row, so any PENDING one reaching this FILTER is
            # overdue by definition.
            func.count(ScheduledDose.id).filter(
                or_(
                    ScheduledDose.status == "MISSED",
                    ScheduledDose.status == "PENDING",
                )
            ),
        ).where(
            ScheduledDose.patient_id == patient_id,
            ScheduledDose.current_scheduled_at >= range_start,
            ScheduledDose.current_scheduled_at < range_end,
            is_due,
            _access_filter(actor_id, ScheduledDose.patient_id),
        )
        result = await self._db.execute(stmt)
        row = result.one()
        return row[0], row[1], row[2], row[3]

    async def list_by_patient(
        self,
        patient_id: uuid.UUID,
        actor_id: uuid.UUID,
        range_start: datetime,
        range_end: datetime,
        page: int = 1,
        size: int = 10,
    ) -> Tuple[List[AdherenceLog], int]:
        """Fetch paginated adherence logs for a patient, newest first.

        Count is a separate query rather than count().over() — the window
        function forces the planner to materialize the full filtered result
        before LIMIT can apply, which is a full scan on every page request.
        Rides idx_adherence_logs_patient_performed (patient_id, performed_at DESC).
        """
        filters = [
            AdherenceLog.patient_id == patient_id,
            AdherenceLog.performed_at >= range_start,
            AdherenceLog.performed_at < range_end,
            _access_filter(actor_id, AdherenceLog.patient_id),
        ]

        count_stmt = select(func.count(AdherenceLog.id)).where(*filters)
        total_count = (await self._db.execute(count_stmt)).scalar_one()

        if total_count == 0:
            return [], 0

        offset = (page - 1) * size
        stmt = (
            select(AdherenceLog)
            .where(*filters)
            .order_by(AdherenceLog.performed_at.desc())
            .offset(offset)
            .limit(size)
        )
        result = await self._db.execute(stmt)
        items = list(result.scalars().all())
        return items, total_count


class HealthSurveyRepository:
    """Repository handling HealthSurvey and SymptomReport database operations."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def create_survey(
        self,
        patient_id: uuid.UUID,
        survey_date,
        answers_json: Dict[str, Any],
    ) -> HealthSurvey:
        """Persist a submitted health survey header.

        submitted_at is set Python-side (not func.now()) — a value assigned
        via a raw SQL expression on an add()+flush() insert is written to the
        row correctly but never read back onto the in-memory ORM attribute
        (unlike a Core update().returning(), which does), so a later
        model_validate() access raises MissingGreenlet trying to lazily
        reload it outside the async context.
        """
        survey = HealthSurvey(
            patient_id=patient_id,
            survey_date=survey_date,
            status="SUBMITTED",
            answers_json=answers_json,
            submitted_at=datetime.now(dt_timezone.utc),
        )
        self._db.add(survey)
        await self._db.flush()
        return survey

    async def bulk_create_symptom_reports(
        self,
        patient_id: uuid.UUID,
        survey_id: uuid.UUID,
        symptoms: List[Dict[str, Any]],
    ) -> List[SymptomReport]:
        """Insert multiple symptom entries in one flush (single round trip,
        not a per-symptom loop) — mirrors PrescriptionRepository.bulk_create_items."""
        if not symptoms:
            return []
        rows = [
            SymptomReport(
                patient_id=patient_id,
                survey_id=survey_id,
                symptom_code=s["symptom_code"],
                severity=s["severity"],
                description=s.get("description"),
                source="HEALTH_SURVEY",
            )
            for s in symptoms
        ]
        self._db.add_all(rows)
        await self._db.flush()
        return rows

    async def get_by_patient_date(
        self, patient_id: uuid.UUID, survey_date
    ) -> Optional[HealthSurvey]:
        """Look up the existing row after a uq_health_surveys_patient_date
        IntegrityError, so the service can turn a double-submit into a 409
        naming the conflicting survey rather than a bare 500."""
        stmt = select(HealthSurvey).where(
            HealthSurvey.patient_id == patient_id,
            HealthSurvey.survey_date == survey_date,
        )
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    def _symptom_count_subquery(survey_id_col: ColumnElement):
        return (
            select(func.count(SymptomReport.id))
            .where(SymptomReport.survey_id == survey_id_col)
            .correlate_except(SymptomReport)
            .scalar_subquery()
        )

    @staticmethod
    def _max_severity_subquery(survey_id_col: ColumnElement):
        """Highest-severity symptom on the survey (SEVERE > MODERATE > MILD),
        as a correlated scalar subquery rather than a join+group so it can't
        multiply survey rows."""
        severity_rank = case(
            (SymptomReport.severity == "SEVERE", 3),
            (SymptomReport.severity == "MODERATE", 2),
            (SymptomReport.severity == "MILD", 1),
            else_=0,
        )
        return (
            select(SymptomReport.severity)
            .where(SymptomReport.survey_id == survey_id_col)
            .order_by(severity_rank.desc())
            .limit(1)
            .correlate_except(SymptomReport)
            .scalar_subquery()
        )

    async def list_surveys_platform(
        self,
        from_date,
        to_date,
        doctor_id: Optional[uuid.UUID] = None,
        patient_id: Optional[uuid.UUID] = None,
        severity: Optional[str] = None,
        page: int = 1,
        size: int = 10,
    ) -> Tuple[List[Tuple[Any, ...]], int]:
        """DOCTOR/ADMIN platform-wide survey list. doctor_id=None means
        unscoped (ADMIN); otherwise restricted to patients this doctor has
        written at least one prescription for, mirroring
        DashboardRepository.list_dashboard_patients.

        Returns (patient_id, patient_name, survey_date, id, status,
        submitted_at, symptom_count, max_severity) rows — same shape
        list_surveys_for_patient returns, so the service maps both with one
        function. Rides idx_health_surveys_date_id for the range+order and
        idx_symptom_reports_severity_survey when severity is filtered.
        """
        filters = [
            HealthSurvey.survey_date >= from_date,
            HealthSurvey.survey_date <= to_date,
        ]
        if doctor_id is not None:
            filters.append(
                select(Prescription.id)
                .where(
                    Prescription.doctor_id == doctor_id,
                    Prescription.patient_id == HealthSurvey.patient_id,
                )
                .exists()
            )
        if patient_id is not None:
            filters.append(HealthSurvey.patient_id == patient_id)
        if severity is not None:
            filters.append(
                select(SymptomReport.id)
                .where(
                    SymptomReport.survey_id == HealthSurvey.id,
                    SymptomReport.severity == severity,
                )
                .exists()
            )

        count_stmt = select(func.count(HealthSurvey.id)).where(*filters)
        total_count = (await self._db.execute(count_stmt)).scalar_one()

        if total_count == 0:
            return [], 0

        symptom_count = self._symptom_count_subquery(HealthSurvey.id)
        max_severity = self._max_severity_subquery(HealthSurvey.id)

        offset = (page - 1) * size
        stmt = (
            select(
                HealthSurvey.patient_id,
                PatientProfile.name,
                HealthSurvey.survey_date,
                HealthSurvey.id,
                HealthSurvey.status,
                HealthSurvey.submitted_at,
                symptom_count,
                max_severity,
            )
            .join(PatientProfile, HealthSurvey.patient_id == PatientProfile.user_id)
            .where(*filters)
            .order_by(HealthSurvey.survey_date.desc(), HealthSurvey.id.desc())
            .offset(offset)
            .limit(size)
        )
        result = await self._db.execute(stmt)
        return list(result.all()), total_count

    async def list_surveys_for_patient(
        self,
        patient_id: uuid.UUID,
        actor_id: uuid.UUID,
        from_date,
        to_date,
        page: int = 1,
        size: int = 10,
    ) -> Tuple[List[Tuple[Any, ...]], int]:
        """PATIENT/DOCTOR/CAREGIVER per-patient survey list, access-scoped
        the same way as adherence data (self / doctor-prescribed /
        active-caregiver). Out-of-scope returns an empty page, mirroring
        AdherenceLogRepository.list_by_patient. Rides
        idx_health_surveys_patient_date."""
        filters = [
            HealthSurvey.patient_id == patient_id,
            HealthSurvey.survey_date >= from_date,
            HealthSurvey.survey_date <= to_date,
            _access_filter(actor_id, HealthSurvey.patient_id),
        ]

        count_stmt = select(func.count(HealthSurvey.id)).where(*filters)
        total_count = (await self._db.execute(count_stmt)).scalar_one()

        if total_count == 0:
            return [], 0

        symptom_count = self._symptom_count_subquery(HealthSurvey.id)
        max_severity = self._max_severity_subquery(HealthSurvey.id)

        offset = (page - 1) * size
        stmt = (
            select(
                HealthSurvey.patient_id,
                PatientProfile.name,
                HealthSurvey.survey_date,
                HealthSurvey.id,
                HealthSurvey.status,
                HealthSurvey.submitted_at,
                symptom_count,
                max_severity,
            )
            .join(PatientProfile, HealthSurvey.patient_id == PatientProfile.user_id)
            .where(*filters)
            .order_by(HealthSurvey.survey_date.desc(), HealthSurvey.id.desc())
            .offset(offset)
            .limit(size)
        )
        result = await self._db.execute(stmt)
        return list(result.all()), total_count

    async def get_survey_detail_scoped(
        self, survey_id: uuid.UUID, actor_id: uuid.UUID
    ) -> Optional[HealthSurvey]:
        """Fetch one survey with its symptom_reports eager-loaded (avoids
        the lazy="raise" trap), scoped the same way as the list endpoints.
        None means not found OR no access — caller turns both into 404."""
        stmt = (
            select(HealthSurvey)
            .options(selectinload(HealthSurvey.symptom_reports))
            .where(
                HealthSurvey.id == survey_id,
                _access_filter(actor_id, HealthSurvey.patient_id),
            )
        )
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()


class AlertRepository:
    """Repository handling Alert (safety escalation) database operations."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def create_alert(
        self,
        patient_id: uuid.UUID,
        triggered_by_type: str,
        alert_type: str,
        severity: str,
        triggered_by_id: Optional[uuid.UUID] = None,
        message: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        idempotency_key: Optional[str] = None,
    ) -> Alert:
        """Insert a new OPEN alert. A duplicate idempotency_key raises
        IntegrityError (uq_alerts_idempotency_key) — caller catches it and
        treats the request as an idempotent replay."""
        alert = Alert(
            patient_id=patient_id,
            triggered_by_type=triggered_by_type,
            triggered_by_id=triggered_by_id,
            alert_type=alert_type,
            severity=severity,
            status="OPEN",
            message=message,
            alert_metadata=metadata or {},
            idempotency_key=idempotency_key,
        )
        self._db.add(alert)
        await self._db.flush()
        return alert

    async def get_by_idempotency_key(self, idempotency_key: str) -> Optional[Alert]:
        stmt = select(Alert).where(Alert.idempotency_key == idempotency_key)
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_id(self, alert_id: uuid.UUID) -> Optional[Alert]:
        """Fetch an alert by ID, unscoped — GET /alerts is DOCTOR/ADMIN-only
        platform-wide (no per-patient ownership restriction in the contract),
        so acknowledge/resolve need no access predicate beyond RBAC."""
        stmt = select(Alert).where(Alert.id == alert_id)
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def acknowledge_if_open(
        self, alert_id: uuid.UUID, doctor_id: uuid.UUID
    ) -> Optional[Alert]:
        """Atomic OPEN -> ACKNOWLEDGED compare-and-swap, assigns the
        acknowledging doctor. Returns None if not found or no longer OPEN
        (already acknowledged/resolved by someone else) — caller
        disambiguates via get_by_id."""
        stmt = (
            update(Alert)
            .where(Alert.id == alert_id, Alert.status == "OPEN")
            .values(status="ACKNOWLEDGED", assigned_doctor_id=doctor_id)
            .returning(Alert)
        )
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def resolve_if_active(
        self, alert_id: uuid.UUID, doctor_id: uuid.UUID
    ) -> Optional[Alert]:
        """Atomic OPEN/ACKNOWLEDGED -> RESOLVED compare-and-swap. Resolving
        directly from OPEN (skipping acknowledge) is allowed — the contract
        does not mandate the intermediate step. assigned_doctor_id keeps
        whoever already acknowledged it (COALESCE) rather than being
        overwritten by whoever resolves it."""
        stmt = (
            update(Alert)
            .where(Alert.id == alert_id, Alert.status.in_(("OPEN", "ACKNOWLEDGED")))
            .values(
                status="RESOLVED",
                assigned_doctor_id=func.coalesce(Alert.assigned_doctor_id, doctor_id),
            )
            .returning(Alert)
        )
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_alerts(
        self,
        status: Optional[str] = None,
        patient_id: Optional[uuid.UUID] = None,
        page: int = 1,
        size: int = 10,
    ) -> Tuple[List[Alert], int]:
        """Fetch paginated alerts, newest first, for the DOCTOR/ADMIN
        dashboard. Rides idx_alerts_status_created / idx_alerts_patient_created
        depending on which filter is supplied.

        Count is a separate query rather than count().over() — the window
        function forces the planner to materialize the full filtered result
        before LIMIT can apply, which is a full scan on every page request.
        """
        filters = []
        if status:
            filters.append(Alert.status == status)
        if patient_id is not None:
            filters.append(Alert.patient_id == patient_id)

        count_stmt = select(func.count(Alert.id))
        if filters:
            count_stmt = count_stmt.where(*filters)
        total_count = (await self._db.execute(count_stmt)).scalar_one()

        if total_count == 0:
            return [], 0

        base_stmt = select(Alert)
        if filters:
            base_stmt = base_stmt.where(*filters)

        offset = (page - 1) * size
        stmt = base_stmt.order_by(Alert.created_at.desc()).offset(offset).limit(size)
        result = await self._db.execute(stmt)
        items = list(result.scalars().all())
        return items, total_count


class NotificationRepository:
    """Repository handling notification deliveries and dose junction items."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def create_grouped_delivery(
        self,
        recipient_user_id: uuid.UUID,
        channel: str,
        template_code: str,
        scheduled_at: datetime,
        title: str,
        body: str,
        scheduled_dose_ids: List[uuid.UUID],
        metadata: Optional[Dict[str, Any]] = None,
        idempotency_key: Optional[str] = None,
    ) -> NotificationDelivery:
        """Create a consolidated notification delivery linked to multiple scheduled doses."""
        delivery = NotificationDelivery(
            recipient_user_id=recipient_user_id,
            channel=channel,
            template_code=template_code,
            title=title,
            body=body,
            delivery_metadata=metadata or {},
            scheduled_at=scheduled_at,
            idempotency_key=idempotency_key,
            status="QUEUED",
        )
        self._db.add(delivery)
        await self._db.flush()

        for dose_id in scheduled_dose_ids:
            item = NotificationDoseItem(
                notification_delivery_id=delivery.id,
                scheduled_dose_id=dose_id,
            )
            self._db.add(item)
        await self._db.flush()
        return delivery

    async def get_delivery_by_id(
        self, delivery_id: uuid.UUID
    ) -> Optional[NotificationDelivery]:
        stmt = select(NotificationDelivery).where(NotificationDelivery.id == delivery_id)
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_delivery_by_idempotency_key(
        self, idempotency_key: str
    ) -> Optional[NotificationDelivery]:
        stmt = select(NotificationDelivery).where(
            NotificationDelivery.idempotency_key == idempotency_key
        )
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_active_fcm_tokens(self, user_id: uuid.UUID) -> List[str]:
        stmt = select(UserDevice.fcm_token).where(
            UserDevice.user_id == user_id,
            UserDevice.is_active.is_(True),
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def update_delivery_status(self, delivery_id: uuid.UUID, status: str) -> None:
        stmt = (
            update(NotificationDelivery)
            .where(NotificationDelivery.id == delivery_id)
            .values(
                status=status,
                sent_at=func.now() if status in ("SENT", "DELIVERED") else None,
            )
        )
        await self._db.execute(stmt)

    async def deactivate_fcm_tokens(self, tokens: List[str]) -> None:
        """Deactivate expired or unregistered FCM tokens to prevent accumulation."""
        if not tokens:
            return
        stmt = (
            update(UserDevice)
            .where(UserDevice.fcm_token.in_(tokens))
            .values(is_active=False, updated_at=datetime.now(dt_timezone.utc))
        )
        await self._db.execute(stmt)

