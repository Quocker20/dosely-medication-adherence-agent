import logging
import uuid
from datetime import datetime, timedelta, timezone as dt_timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import Exists, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from src.modules.adherence.models import AdherenceLog, Alert, HealthSurvey, SymptomReport
from src.modules.agents.models import ScheduledDose
from src.modules.patients.models import CaregiverLink, PatientProfile
from src.modules.prescriptions.models import Prescription

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
        """Atomic compare-and-swap: only updates a row still PENDING and
        owned by this patient — no read-then-write race window (mirrors
        PrescriptionRepository.approve_if_draft). Returns None if the dose
        doesn't exist, isn't this patient's, or is no longer PENDING; caller
        (service) disambiguates via get_dose_scoped.

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
            )
            .values(**values)
            .returning(ScheduledDose)
        )
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

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

    async def get_log_by_idempotency_key(self, idempotency_key: str) -> Optional[AdherenceLog]:
        stmt = select(AdherenceLog).where(AdherenceLog.idempotency_key == idempotency_key)
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_dose_status_counts(
        self,
        patient_id: uuid.UUID,
        actor_id: uuid.UUID,
        range_start: datetime,
        range_end: datetime,
    ) -> Tuple[int, int, int, int]:
        """Single aggregate query (one round trip, FILTER-based conditional
        counts) returning (total, taken, skipped, missed) doses scheduled in
        [range_start, range_end) — avoids running four separate COUNT
        queries. Rides idx_scheduled_doses_patient_time (patient_id,
        current_scheduled_at)."""
        stmt = select(
            func.count(ScheduledDose.id),
            func.count(ScheduledDose.id).filter(ScheduledDose.status == "TAKEN"),
            func.count(ScheduledDose.id).filter(ScheduledDose.status == "SKIPPED"),
            func.count(ScheduledDose.id).filter(ScheduledDose.status == "MISSED"),
        ).where(
            ScheduledDose.patient_id == patient_id,
            ScheduledDose.current_scheduled_at >= range_start,
            ScheduledDose.current_scheduled_at < range_end,
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
