import logging
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import Exists, delete, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from src.modules.agents.models import AgentRun, ScheduledDose
from src.modules.patients.models import CaregiverLink, PatientProfile, PatientRoutine
from src.modules.prescriptions.models import Prescription, PrescriptionItem

logger = logging.getLogger(__name__)


class AgentRunRepository:
    """Repository handling AgentRun database operations."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def create_run(
        self,
        patient_id: uuid.UUID,
        agent_type: str,
        trigger_type: str,
        graph_version: str,
        prescription_id: uuid.UUID | None = None,
    ) -> AgentRun:
        """Insert a RUNNING agent run row. IntegrityError on
        uq_agent_runs_one_running means the patient already has an in-flight
        run — caller (service) turns that into 409 Conflict."""
        run = AgentRun(
            patient_id=patient_id,
            prescription_id=prescription_id,
            agent_type=agent_type,
            trigger_type=trigger_type,
            graph_version=graph_version,
            status="RUNNING",
        )
        self._db.add(run)
        await self._db.flush()
        return run

    async def get_by_id(self, agent_run_id: uuid.UUID, actor_id: uuid.UUID | None = None) -> AgentRun | None:
        """Fetch a run by ID. actor_id=None means unscoped (ADMIN);
        otherwise restricted to the patient themselves or a doctor who has
        prescribed for that patient — matches the contract's
        PATIENT/DOCTOR/ADMIN constraint (no CAREGIVER) for this endpoint."""
        stmt = select(AgentRun).where(AgentRun.id == agent_run_id)
        if actor_id is not None:
            stmt = stmt.where(
                or_(
                    AgentRun.patient_id == actor_id,
                    self._has_prescribed_filter(actor_id, AgentRun.patient_id),
                )
            )
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_id_unscoped(self, agent_run_id: uuid.UUID) -> AgentRun | None:
        """Fetch a run by ID with no access check — used by the worker task,
        which already knows its own run_id and needs no caller-scoping."""
        result = await self._db.execute(select(AgentRun).where(AgentRun.id == agent_run_id))
        return result.scalar_one_or_none()

    async def claim_run(self, run_id: uuid.UUID, lease_seconds: int) -> AgentRun | None:
        """Claim an unowned or expired RUNNING run with a renewable token."""
        claim_token = uuid.uuid4()
        stmt = (
            update(AgentRun)
            .where(
                AgentRun.id == run_id,
                AgentRun.status == "RUNNING",
                or_(
                    AgentRun.claim_expires_at.is_(None),
                    AgentRun.claim_expires_at < func.now(),
                ),
            )
            .values(
                started_at=func.coalesce(AgentRun.started_at, func.now()),
                claim_token=claim_token,
                claim_expires_at=func.now() + timedelta(seconds=lease_seconds),
            )
            .returning(AgentRun)
        )
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def renew_claim(
        self,
        run_id: uuid.UUID,
        claim_token: uuid.UUID,
        lease_seconds: int,
    ) -> bool:
        """Renew only the current owner's claim and lock it through commit."""
        stmt = (
            update(AgentRun)
            .where(
                AgentRun.id == run_id,
                AgentRun.status == "RUNNING",
                AgentRun.claim_token == claim_token,
            )
            .values(claim_expires_at=func.now() + timedelta(seconds=lease_seconds))
            .returning(AgentRun.id)
        )
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def mark_completed(
        self,
        run_id: uuid.UUID,
        latency_ms: int,
        generated_dose_count: int,
        *,
        model_version: str | None = None,
        prompt_version: str | None = None,
        input_hash: str | None = None,
        output_hash: str | None = None,
        candidate_source: str | None = None,
        error_code: str | None = None,
        claim_token: uuid.UUID | None = None,
    ) -> bool:
        stmt = (
            update(AgentRun)
            .where(AgentRun.id == run_id)
            .values(
                status="COMPLETED",
                latency_ms=latency_ms,
                generated_dose_count=generated_dose_count,
                model_version=model_version,
                prompt_version=prompt_version,
                input_hash=input_hash,
                output_hash=output_hash,
                candidate_source=candidate_source,
                error_code=error_code,
                claim_expires_at=None,
            )
            .returning(AgentRun.id)
        )
        if claim_token is not None:
            stmt = stmt.where(AgentRun.claim_token == claim_token)
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def mark_failed(
        self,
        run_id: uuid.UUID,
        latency_ms: int,
        error_code: str,
        error_message: str | None = None,
        claim_token: uuid.UUID | None = None,
        **audit: Any,
    ) -> bool:
        stmt = update(AgentRun).where(AgentRun.id == run_id)
        if claim_token is not None:
            stmt = stmt.where(AgentRun.claim_token == claim_token)
        stmt = stmt.values(
            status="FAILED",
            latency_ms=latency_ms,
            error_code=error_code,
            error_message=error_message,
            claim_expires_at=None,
            **audit,
        ).returning(AgentRun.id)
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def mark_needs_review(
        self,
        run_id: uuid.UUID,
        latency_ms: int,
        error_code: str,
        error_message: str | None = None,
        claim_token: uuid.UUID | None = None,
        **audit: Any,
    ) -> bool:
        """Persist a safe terminal state for deterministic planning conflicts."""
        stmt = (
            update(AgentRun)
            .where(AgentRun.id == run_id)
            .values(
                status="NEEDS_REVIEW",
                latency_ms=latency_ms,
                error_code=error_code,
                error_message=error_message,
                generated_dose_count=0,
                claim_expires_at=None,
                **audit,
            )
            .returning(AgentRun.id)
        )
        if claim_token is not None:
            stmt = stmt.where(AgentRun.claim_token == claim_token)
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none() is not None

    @staticmethod
    def _has_prescribed_filter(doctor_id: uuid.UUID, patient_id_col: ColumnElement) -> Exists:
        """Mirrors PrescriptionRepository._has_prescribed_filter (duplicated
        per structure.md's vertical-slice isolation). Correlated on
        patient_id_col rather than agent_runs.prescription_id — the latter
        goes NULL on ON DELETE SET NULL and would silently revoke a doctor's
        access to a run for a patient they still legitimately treat."""
        return (
            select(Prescription.id)
            .where(
                Prescription.doctor_id == doctor_id,
                Prescription.patient_id == patient_id_col,
            )
            .exists()
        )


class ScheduledDoseRepository:
    """Repository handling ScheduledDose database operations."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    @staticmethod
    def _has_prescribed_filter(doctor_id: uuid.UUID, patient_id_col: ColumnElement) -> Exists:
        return (
            select(Prescription.id)
            .where(
                Prescription.doctor_id == doctor_id,
                Prescription.patient_id == patient_id_col,
            )
            .exists()
        )

    @staticmethod
    def _has_active_caregiver_filter(caregiver_user_id: uuid.UUID, patient_id_col: ColumnElement) -> Exists:
        return (
            select(CaregiverLink.id)
            .where(
                CaregiverLink.caregiver_user_id == caregiver_user_id,
                CaregiverLink.patient_id == patient_id_col,
                CaregiverLink.status == "ACTIVE",
            )
            .exists()
        )

    @classmethod
    def _access_filter(cls, actor_id: uuid.UUID, patient_id_col: ColumnElement):
        """Role-agnostic access predicate, mirrors
        PrescriptionRepository._access_filter: self-owned, doctor-prescribed,
        or active-caregiver-linked are independent facts checked together."""
        return or_(
            patient_id_col == actor_id,
            cls._has_prescribed_filter(actor_id, patient_id_col),
            cls._has_active_caregiver_filter(actor_id, patient_id_col),
        )

    async def get_patient_timezone_scoped(self, patient_id: uuid.UUID, actor_id: uuid.UUID) -> str | None:
        """Fetch a patient's timezone, access-scoped the same way as the
        schedule query itself — never leak timezone to a caller who
        couldn't read the schedule anyway. None means not found OR no
        access (indistinguishable, blocks UUID probing)."""
        stmt = select(PatientProfile.timezone).where(
            PatientProfile.user_id == patient_id,
            self._access_filter(actor_id, PatientProfile.user_id),
        )
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_patient_context_unscoped(
        self,
        patient_id: uuid.UUID,
        *,
        for_update: bool = False,
    ) -> tuple[str | None, PatientRoutine | None]:
        """Fetch (timezone, routine) with no access check — used by the
        worker task, which runs for a run_id/patient_id the service already
        validated when the run was created."""
        tz_stmt = select(PatientProfile.timezone).where(PatientProfile.user_id == patient_id)
        if for_update:
            tz_stmt = tz_stmt.with_for_update()
        tz_result = await self._db.execute(tz_stmt)
        patient_timezone = tz_result.scalar_one_or_none()

        routine_stmt = select(PatientRoutine).where(PatientRoutine.patient_id == patient_id)
        if for_update:
            routine_stmt = routine_stmt.with_for_update()
        routine_result = await self._db.execute(routine_stmt)
        routine = routine_result.scalar_one_or_none()

        return patient_timezone, routine

    async def get_approved_items(
        self,
        patient_id: uuid.UUID,
        *,
        for_update: bool = False,
    ) -> list[tuple[PrescriptionItem, uuid.UUID]]:
        """Fetch every PrescriptionItem belonging to an APPROVED prescription
        for this patient — HITL: DRAFT/CANCELLED prescriptions generate no
        doses. Returns (item, prescription_id) pairs."""
        stmt = (
            select(PrescriptionItem, Prescription.id)
            .join(Prescription, PrescriptionItem.prescription_id == Prescription.id)
            .where(Prescription.patient_id == patient_id, Prescription.status == "APPROVED")
            .order_by(PrescriptionItem.id.asc())
        )
        if for_update:
            stmt = stmt.with_for_update(of=[Prescription, PrescriptionItem])
        result = await self._db.execute(stmt)
        return [(row[0], row[1]) for row in result.all()]

    async def bulk_insert_doses(self, rows: list[dict[str, Any]]) -> int:
        """Insert generated doses, skipping any that collide with an
        existing (prescription_item_id, original_scheduled_at) pair
        (uq_scheduled_doses_item_original) — makes a retried/duplicated
        generation idempotent instead of double-booking. Returns the count
        actually inserted (collisions excluded)."""
        if not rows:
            return 0
        stmt = (
            pg_insert(ScheduledDose)
            .values(rows)
            .on_conflict_do_nothing(index_elements=["prescription_item_id", "original_scheduled_at"])
            .returning(ScheduledDose.id)
        )
        result = await self._db.execute(stmt)
        return len(result.all())

    async def delete_future_pending(self, patient_id: uuid.UUID, now: datetime) -> None:
        """Wipe only PENDING doses not yet due, ahead of a reschedule
        regeneration. Past doses and anything already actioned
        (TAKEN/SKIPPED/MISSED) are never touched, keeping adherence history
        intact."""
        stmt = delete(ScheduledDose).where(
            ScheduledDose.patient_id == patient_id,
            ScheduledDose.status == "PENDING",
            ScheduledDose.current_scheduled_at > now,
        )
        await self._db.execute(stmt)

    async def lock_reschedule_window(self, patient_id: uuid.UUID, now: datetime) -> list[ScheduledDose]:
        """Lock future rows plus the latest retained row for every item.

        The lock serializes dose actions with rescheduling, preventing a row
        from becoming TAKEN/SKIPPED between the retained snapshot and delete.
        Selecting the latest past row per item avoids a fixed lookback when an
        approved minimum interval is longer than one day.
        """
        rank = (
            func.row_number()
            .over(
                partition_by=ScheduledDose.prescription_item_id,
                order_by=ScheduledDose.current_scheduled_at.desc(),
            )
            .label("rn")
        )
        latest_past = (
            select(ScheduledDose.id.label("dose_id"), rank)
            .where(
                ScheduledDose.patient_id == patient_id,
                ScheduledDose.current_scheduled_at <= now,
            )
            .subquery()
        )
        latest_past_ids = select(latest_past.c.dose_id).where(latest_past.c.rn == 1)
        stmt = (
            select(ScheduledDose)
            .where(
                ScheduledDose.patient_id == patient_id,
                or_(
                    ScheduledDose.current_scheduled_at > now,
                    ScheduledDose.id.in_(latest_past_ids),
                ),
            )
            .order_by(ScheduledDose.current_scheduled_at.asc())
            .with_for_update()
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def delete_future_pending_for_prescription(self, prescription_id: uuid.UUID, now: datetime) -> None:
        """Wipe only this prescription's future PENDING doses, ahead of a
        cancel — sibling of delete_future_pending, scoped to one
        prescription instead of the whole patient (the patient can have
        other still-active prescriptions whose doses must survive). Without
        this, a cancelled prescription's already-generated doses sit PENDING
        forever and the missed-dose scan (MissedDoseScanService) eventually
        marks them MISSED and raises a Red Alert for medication the patient
        is no longer even supposed to take."""
        stmt = delete(ScheduledDose).where(
            ScheduledDose.status == "PENDING",
            ScheduledDose.current_scheduled_at > now,
            ScheduledDose.prescription_item_id.in_(
                select(PrescriptionItem.id).where(PrescriptionItem.prescription_id == prescription_id)
            ),
        )
        await self._db.execute(stmt)

    async def get_schedule_in_range(
        self,
        patient_id: uuid.UUID,
        range_start: datetime,
        range_end: datetime,
        actor_id: uuid.UUID | None = None,
    ) -> list[tuple[ScheduledDose, str]]:
        """Fetch a patient's doses within [range_start, range_end).

        The ORM row carries immutable slot/dose snapshots; the join is only
        for PrescriptionItem.display_name and is never used to infer an
        amount. Caller (service)
        computes the range from the patient's own timezone — a "date" query
        param is a local calendar date, not a UTC one, so the boundary must
        not be assumed here. actor_id=None means unscoped (ADMIN)."""
        stmt = (
            select(ScheduledDose, PrescriptionItem.display_name)
            .join(
                PrescriptionItem,
                ScheduledDose.prescription_item_id == PrescriptionItem.id,
            )
            .where(
                ScheduledDose.patient_id == patient_id,
                ScheduledDose.current_scheduled_at >= range_start,
                ScheduledDose.current_scheduled_at < range_end,
            )
        )
        if actor_id is not None:
            stmt = stmt.where(self._access_filter(actor_id, ScheduledDose.patient_id))
        stmt = stmt.order_by(ScheduledDose.current_scheduled_at.asc())
        result = await self._db.execute(stmt)
        return [(row[0], row[1]) for row in result.all()]

    async def mark_overdue_pending_as_missed(self, cutoff: datetime) -> list[tuple[uuid.UUID, uuid.UUID, datetime]]:
        """Flip every ScheduledDose still PENDING with current_scheduled_at <
        cutoff to MISSED, across all patients in one statement. Rides
        idx_scheduled_doses_pending_due (current_scheduled_at) WHERE
        status='PENDING'. Race-safe against a patient actioning the same dose
        concurrently: standard row-level UPDATE locking means a row already
        flipped to TAKEN/SKIPPED a moment earlier no longer matches
        status='PENDING' by the time this runs, so it's simply excluded — no
        read-then-write window. Returns (patient_id, dose_id,
        current_scheduled_at) for every row just flipped, so the caller only
        recomputes streaks for affected patients."""
        stmt = (
            update(ScheduledDose)
            .where(
                ScheduledDose.status == "PENDING",
                ScheduledDose.current_scheduled_at < cutoff,
            )
            .values(status="MISSED")
            .returning(
                ScheduledDose.patient_id,
                ScheduledDose.id,
                ScheduledDose.current_scheduled_at,
            )
        )
        result = await self._db.execute(stmt)
        return [(row[0], row[1], row[2]) for row in result.all()]

    async def get_recent_dose_statuses(
        self, patient_ids: list[uuid.UUID], lookback: int, before: datetime
    ) -> dict[uuid.UUID, list[dict[str, str]]]:
        """For each patient_id, fetch their most recent `lookback` doses at
        or before `before` (ascending, as {"status": ...} dicts — feeds
        count_missed_dose_streak directly). One query for all affected
        patients via ROW_NUMBER() OVER (PARTITION BY patient_id ...), not one
        query per patient. `lookback` is meant to be
        settings.missed_dose_alert_threshold — we only ever need to know
        whether the *last N* doses are all SKIPPED/MISSED, so fetching
        exactly N rows/patient bounds this query regardless of history
        length.

        `before` (pass the scan's own "now") is required, not optional: a
        patient's rolling schedule already has PENDING doses generated days
        into the future (schedule_horizon_days), and ORDER BY
        current_scheduled_at DESC ranks a distant future timestamp above any
        past one — without this filter the "most recent N" doses would
        actually be the *furthest-future* N, all still PENDING, which zeroes
        out count_missed_dose_streak on the very first (still-PENDING)
        element and masks a real streak sitting just before them."""
        if not patient_ids:
            return {}
        rn = (
            func.row_number()
            .over(
                partition_by=ScheduledDose.patient_id,
                order_by=ScheduledDose.current_scheduled_at.desc(),
            )
            .label("rn")
        )
        subq = (
            select(
                ScheduledDose.patient_id,
                ScheduledDose.status,
                ScheduledDose.current_scheduled_at,
                rn,
            )
            .where(
                ScheduledDose.patient_id.in_(patient_ids),
                ScheduledDose.current_scheduled_at <= before,
            )
            .subquery()
        )
        stmt = (
            select(subq.c.patient_id, subq.c.status)
            .where(subq.c.rn <= lookback)
            .order_by(subq.c.patient_id, subq.c.current_scheduled_at.asc())
        )
        result = await self._db.execute(stmt)
        grouped: dict[uuid.UUID, list[dict[str, str]]] = {}
        for patient_id, status in result.all():
            grouped.setdefault(patient_id, []).append({"status": status})
        return grouped

    async def get_due_dose_groups(
        self, cutoff: datetime
    ) -> Dict[Tuple[uuid.UUID, datetime], List[Dict[str, Any]]]:
        """Fetch all PENDING doses due at or before cutoff, grouped by
        (patient_id, current_scheduled_at). Each group contains the individual
        scheduled doses with medication display name and dosage snapshot,
        ready for consolidating into a single push notification delivery."""
        stmt = (
            select(ScheduledDose, PrescriptionItem.display_name)
            .join(
                PrescriptionItem,
                ScheduledDose.prescription_item_id == PrescriptionItem.id,
            )
            .where(
                ScheduledDose.status == "PENDING",
                ScheduledDose.current_scheduled_at <= cutoff,
            )
            .order_by(
                ScheduledDose.patient_id,
                ScheduledDose.current_scheduled_at,
                ScheduledDose.id,
            )
        )
        result = await self._db.execute(stmt)
        grouped: Dict[Tuple[uuid.UUID, datetime], List[Dict[str, Any]]] = {}
        for dose, medication_name in result.all():
            key = (dose.patient_id, dose.current_scheduled_at)
            grouped.setdefault(key, []).append(
                {
                    "scheduled_dose_id": dose.id,
                    "prescription_item_id": dose.prescription_item_id,
                    "medication_id": dose.medication_id,
                    "medication_name": medication_name,
                    "current_scheduled_at": dose.current_scheduled_at,
                    "dose_slot": dose.dose_slot,
                    "dose_value": dose.dose_value,
                    "dose_unit": dose.dose_unit,
                    "meal_relation": dose.meal_relation,
                    "snooze_count": dose.snooze_count,
                    "status": dose.status,
                }
            )
        return grouped

