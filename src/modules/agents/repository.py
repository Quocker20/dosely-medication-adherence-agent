import logging
import uuid
from datetime import datetime
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
        prescription_id: Optional[uuid.UUID] = None,
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

    async def get_by_id(
        self, agent_run_id: uuid.UUID, actor_id: Optional[uuid.UUID] = None
    ) -> Optional[AgentRun]:
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

    async def get_by_id_unscoped(self, agent_run_id: uuid.UUID) -> Optional[AgentRun]:
        """Fetch a run by ID with no access check — used by the worker task,
        which already knows its own run_id and needs no caller-scoping."""
        result = await self._db.execute(select(AgentRun).where(AgentRun.id == agent_run_id))
        return result.scalar_one_or_none()

    async def mark_completed(
        self, run_id: uuid.UUID, latency_ms: int, generated_dose_count: int
    ) -> None:
        stmt = (
            update(AgentRun)
            .where(AgentRun.id == run_id)
            .values(
                status="COMPLETED",
                latency_ms=latency_ms,
                generated_dose_count=generated_dose_count,
            )
        )
        await self._db.execute(stmt)

    async def mark_failed(self, run_id: uuid.UUID, latency_ms: int, error_code: str) -> None:
        stmt = (
            update(AgentRun)
            .where(AgentRun.id == run_id)
            .values(status="FAILED", latency_ms=latency_ms, error_code=error_code)
        )
        await self._db.execute(stmt)

    @staticmethod
    def _has_prescribed_filter(
        doctor_id: uuid.UUID, patient_id_col: ColumnElement
    ) -> Exists:
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
    def _has_prescribed_filter(
        doctor_id: uuid.UUID, patient_id_col: ColumnElement
    ) -> Exists:
        return (
            select(Prescription.id)
            .where(
                Prescription.doctor_id == doctor_id,
                Prescription.patient_id == patient_id_col,
            )
            .exists()
        )

    @staticmethod
    def _has_active_caregiver_filter(
        caregiver_user_id: uuid.UUID, patient_id_col: ColumnElement
    ) -> Exists:
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

    async def get_patient_timezone_scoped(
        self, patient_id: uuid.UUID, actor_id: uuid.UUID
    ) -> Optional[str]:
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
        self, patient_id: uuid.UUID
    ) -> Tuple[Optional[str], Optional[PatientRoutine]]:
        """Fetch (timezone, routine) with no access check — used by the
        worker task, which runs for a run_id/patient_id the service already
        validated when the run was created."""
        tz_stmt = select(PatientProfile.timezone).where(PatientProfile.user_id == patient_id)
        tz_result = await self._db.execute(tz_stmt)
        patient_timezone = tz_result.scalar_one_or_none()

        routine_stmt = select(PatientRoutine).where(PatientRoutine.patient_id == patient_id)
        routine_result = await self._db.execute(routine_stmt)
        routine = routine_result.scalar_one_or_none()

        return patient_timezone, routine

    async def get_approved_items(
        self, patient_id: uuid.UUID
    ) -> List[Tuple[PrescriptionItem, uuid.UUID]]:
        """Fetch every PrescriptionItem belonging to an APPROVED prescription
        for this patient — HITL: DRAFT/CANCELLED prescriptions generate no
        doses. Returns (item, prescription_id) pairs."""
        stmt = (
            select(PrescriptionItem, Prescription.id)
            .join(Prescription, PrescriptionItem.prescription_id == Prescription.id)
            .where(Prescription.patient_id == patient_id, Prescription.status == "APPROVED")
        )
        result = await self._db.execute(stmt)
        return [(row[0], row[1]) for row in result.all()]

    async def bulk_insert_doses(self, rows: List[Dict[str, Any]]) -> int:
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

    async def delete_future_pending_for_prescription(
        self, prescription_id: uuid.UUID, now: datetime
    ) -> None:
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
                select(PrescriptionItem.id).where(
                    PrescriptionItem.prescription_id == prescription_id
                )
            ),
        )
        await self._db.execute(stmt)

    async def get_schedule_in_range(
        self,
        patient_id: uuid.UUID,
        range_start: datetime,
        range_end: datetime,
        actor_id: Optional[uuid.UUID] = None,
    ) -> List[Tuple[ScheduledDose, str]]:
        """Fetch a patient's doses within [range_start, range_end), joined to
        PrescriptionItem.display_name for the response. Caller (service)
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

    async def mark_overdue_pending_as_missed(
        self, cutoff: datetime
    ) -> List[Tuple[uuid.UUID, uuid.UUID, datetime]]:
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
        self, patient_ids: List[uuid.UUID], lookback: int
    ) -> Dict[uuid.UUID, List[Dict[str, str]]]:
        """For each patient_id, fetch their most recent `lookback` doses by
        current_scheduled_at (ascending, as {"status": ...} dicts — feeds
        count_missed_dose_streak directly). One query for all affected
        patients via ROW_NUMBER() OVER (PARTITION BY patient_id ...), not one
        query per patient. `lookback` is meant to be
        settings.missed_dose_alert_threshold — we only ever need to know
        whether the *last N* doses are all SKIPPED/MISSED, so fetching
        exactly N rows/patient bounds this query regardless of history
        length."""
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
            .where(ScheduledDose.patient_id.in_(patient_ids))
            .subquery()
        )
        stmt = (
            select(subq.c.patient_id, subq.c.status)
            .where(subq.c.rn <= lookback)
            .order_by(subq.c.patient_id, subq.c.current_scheduled_at.asc())
        )
        result = await self._db.execute(stmt)
        grouped: Dict[uuid.UUID, List[Dict[str, str]]] = {}
        for patient_id, status in result.all():
            grouped.setdefault(patient_id, []).append({"status": status})
        return grouped
