import logging
import uuid
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

from sqlalchemy import Exists, and_, delete, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from src.modules.agents.models import AgentRun, ChatConversation, ChatMessage, ScheduledDose
from src.modules.patients.models import CaregiverLink, PatientProfile, PatientRoutine, RoutineOverride
from src.modules.prescriptions.models import Prescription, PrescriptionItem

logger = logging.getLogger(__name__)


def generate_conversation_title(message: str, max_length: int = 50) -> str:
    """Deterministic local summarizer (trim, collapse spaces, limit to max_length)."""
    cleaned = " ".join(message.strip().split())
    if not cleaned:
        return "Cuộc trò chuyện mới"
    if len(cleaned) <= max_length:
        return cleaned
    return cleaned[: max_length - 3].rstrip() + "..."


class ChatMemoryRepository:
    """Durable chat history scoped to the authenticated patient."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get_or_create(self, patient_id: uuid.UUID, conversation_id: uuid.UUID | None) -> ChatConversation:
        if conversation_id:
            row = await self._db.get(ChatConversation, conversation_id)
            if row is not None and row.patient_id != patient_id:
                raise PermissionError("Conversation does not belong to the authenticated patient")
            if row is None:
                row = ChatConversation(id=conversation_id, patient_id=patient_id)
                self._db.add(row)
                await self._db.flush()
            return row
        row = ChatConversation(patient_id=patient_id)
        self._db.add(row)
        await self._db.flush()
        return row

    async def get_conversation(self, patient_id: uuid.UUID, conversation_id: uuid.UUID) -> ChatConversation | None:
        """Fetch a conversation and enforce patient ownership."""
        row = await self._db.get(ChatConversation, conversation_id)
        if row is not None and row.patient_id != patient_id:
            raise PermissionError("Conversation does not belong to the authenticated patient")
        return row

    async def recent_messages(self, conversation_id: uuid.UUID, limit: int = 10) -> list[ChatMessage]:
        rows = (
            await self._db.scalars(
                select(ChatMessage)
                .where(ChatMessage.conversation_id == conversation_id)
                .order_by(ChatMessage.created_at.desc())
                .limit(limit)
            )
        ).all()
        return list(reversed(rows))

    async def get_history(self, patient_id: uuid.UUID, conversation_id: uuid.UUID) -> list[ChatMessage]:
        """Load durable history only when the conversation belongs to patient."""
        conversation = await self._db.scalar(
            select(ChatConversation).where(
                ChatConversation.id == conversation_id,
                ChatConversation.patient_id == patient_id,
            )
        )
        if conversation is None:
            raise PermissionError("Conversation does not belong to the authenticated patient")
        rows = (await self._db.scalars(
            select(ChatMessage).where(ChatMessage.conversation_id == conversation_id)
            .order_by(ChatMessage.created_at.asc())
        )).all()
        return list(rows)

    async def append_exchange(self, conversation_id: uuid.UUID, question: str, answer: str, intent: str | None) -> None:
        conv = await self._db.get(ChatConversation, conversation_id)
        if conv is not None:
            conv.updated_at = datetime.now(UTC)
            if not conv.summary:
                conv.summary = generate_conversation_title(question)

        self._db.add_all(
            [
                ChatMessage(conversation_id=conversation_id, role="user", content=question, intent=intent),
                ChatMessage(conversation_id=conversation_id, role="assistant", content=answer, intent=intent),
            ]
        )
        await self._db.flush()

    async def list_conversations(
        self,
        patient_id: uuid.UUID,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        """List conversations for the patient, ordered by updated_at desc."""
        total_stmt = select(func.count(ChatConversation.id)).where(ChatConversation.patient_id == patient_id)
        total_count = (await self._db.execute(total_stmt)).scalar_one() or 0

        if total_count == 0:
            return [], 0

        conv_stmt = (
            select(ChatConversation)
            .where(ChatConversation.patient_id == patient_id)
            .order_by(ChatConversation.updated_at.desc())
            .offset((page - 1) * size)
            .limit(size)
        )
        convs = (await self._db.scalars(conv_stmt)).all()
        conv_ids = [c.id for c in convs]

        counts: dict[uuid.UUID, int] = {}
        previews: dict[uuid.UUID, str] = {}

        if conv_ids:
            count_rows = (
                await self._db.execute(
                    select(ChatMessage.conversation_id, func.count(ChatMessage.id))
                    .where(ChatMessage.conversation_id.in_(conv_ids))
                    .group_by(ChatMessage.conversation_id)
                )
            ).all()
            counts = {row[0]: row[1] for row in count_rows}

            latest_subq = (
                select(
                    ChatMessage.conversation_id,
                    ChatMessage.content,
                    func.row_number()
                    .over(
                        partition_by=ChatMessage.conversation_id,
                        order_by=ChatMessage.created_at.desc(),
                    )
                    .label("rn"),
                )
                .where(ChatMessage.conversation_id.in_(conv_ids))
                .subquery()
            )
            latest_rows = (
                await self._db.execute(
                    select(latest_subq.c.conversation_id, latest_subq.c.content).where(latest_subq.c.rn == 1)
                )
            ).all()
            previews = {row[0]: row[1] for row in latest_rows}

        result: list[dict[str, Any]] = []
        for conv in convs:
            preview = previews.get(conv.id)
            title = conv.summary or (generate_conversation_title(preview) if preview else "Cuộc trò chuyện mới")
            result.append(
                {
                    "id": conv.id,
                    "title": title,
                    "preview": preview,
                    "message_count": counts.get(conv.id, 0),
                    "created_at": conv.created_at,
                    "updated_at": conv.updated_at,
                }
            )

        return result, total_count

    async def get_messages_paginated(
        self,
        conversation_id: uuid.UUID,
        limit: int = 50,
        before: str | None = None,
    ) -> tuple[list[ChatMessage], bool, str | None]:
        """Fetch messages paginated backwards (cursor based on created_at / id)."""
        where_clauses = [ChatMessage.conversation_id == conversation_id]

        if before:
            # Check if before is a UUID or ISO datetime string
            cursor_dt = None
            cursor_uuid = None
            try:
                cursor_uuid = uuid.UUID(before)
                cursor_msg = await self._db.get(ChatMessage, cursor_uuid)
                if cursor_msg is not None:
                    cursor_dt = cursor_msg.created_at
            except ValueError:
                try:
                    cursor_dt = datetime.fromisoformat(before)
                except ValueError:
                    cursor_dt = None

            if cursor_dt is not None:
                if cursor_uuid is not None:
                    where_clauses.append(
                        or_(
                            ChatMessage.created_at < cursor_dt,
                            and_(
                                ChatMessage.created_at == cursor_dt,
                                ChatMessage.id < cursor_uuid,
                            ),
                        )
                    )
                else:
                    where_clauses.append(ChatMessage.created_at < cursor_dt)

        stmt = (
            select(ChatMessage)
            .where(*where_clauses)
            .order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc())
            .limit(limit + 1)
        )
        rows = (await self._db.scalars(stmt)).all()
        has_more = len(rows) > limit
        page_rows = rows[:limit]

        # Order messages chronologically (oldest to newest) for presentation
        messages = list(reversed(page_rows))
        next_cursor = str(page_rows[-1].id) if has_more and page_rows else None

        return messages, has_more, next_cursor


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

    async def get_active_overrides(
        self,
        patient_id: uuid.UUID,
        *,
        start: date,
        end: date,
        for_update: bool = False,
    ) -> dict[date, dict[str, time]]:
        """Fetch every RoutineOverride row for this patient in [start, end],
        grouped into the {day: {anchor: time}} shape expand_schedule expects.
        `for_update` locks the rows under the same commit transaction that
        locks routine/prescription inputs (planning_lock_and_revalidate_node)."""
        stmt = select(RoutineOverride).where(
            RoutineOverride.patient_id == patient_id,
            RoutineOverride.override_date >= start,
            RoutineOverride.override_date <= end,
            # A REJECTED row is one a previous run could not schedule safely.
            # Excluding it here is what stops it from being silently retried
            # by an unrelated later reschedule.
            RoutineOverride.status == "ACTIVE",
        )
        if for_update:
            stmt = stmt.with_for_update()
        result = await self._db.execute(stmt)
        overrides: dict[date, dict[str, time]] = {}
        for row in result.scalars().all():
            overrides.setdefault(row.override_date, {})[row.anchor] = row.overridden_time
        return overrides

    async def get_recent_overrides_for_anchor(
        self, patient_id: uuid.UUID, anchor: str, today: date, limit: int = 5
    ) -> list[tuple[date, time]]:
        """Most recent past RoutineOverride entries for one anchor — read-only
        context for the chatbot's clarifying-question phrasing, never used to
        auto-apply a time (see rescheduling_node.py).

        `today` bounds the query to entries that have actually happened. Once
        overrides can be booked ahead, an unbounded DESC scan would surface a
        future booking as "what you usually do", and the suggestion would be
        built from a plan rather than from history.
        """
        stmt = (
            select(RoutineOverride.override_date, RoutineOverride.overridden_time)
            .where(
                RoutineOverride.patient_id == patient_id,
                RoutineOverride.anchor == anchor,
                RoutineOverride.override_date <= today,
            )
            .order_by(RoutineOverride.override_date.desc())
            .limit(limit)
        )
        result = await self._db.execute(stmt)
        return [(row[0], row[1]) for row in result.all()]

    async def upsert_override(
        self,
        patient_id: uuid.UUID,
        override_date: date,
        anchor: str,
        overridden_time: time,
        source: str,
        reason: str | None,
        consumed_by_run_id: uuid.UUID,
    ) -> RoutineOverride:
        """Insert or correct an override for this anchor — re-reporting the
        same (patient, date, anchor) updates the time rather than duplicating
        a row.

        The conflict branch resets status to ACTIVE and re-points
        consumed_by_run_id at the new run on purpose: the patient has just
        reported a *different* time, so a previous rejection no longer
        describes what is now stored, and the stale run id would otherwise
        make the audit trail point at a run that never saw this value.
        """
        stmt = (
            pg_insert(RoutineOverride)
            .values(
                patient_id=patient_id,
                override_date=override_date,
                anchor=anchor,
                overridden_time=overridden_time,
                source=source,
                reason=reason,
                status="ACTIVE",
                consumed_by_run_id=consumed_by_run_id,
            )
            .on_conflict_do_update(
                index_elements=["patient_id", "override_date", "anchor"],
                set_={
                    "overridden_time": overridden_time,
                    "source": source,
                    "reason": reason,
                    "status": "ACTIVE",
                    "consumed_by_run_id": consumed_by_run_id,
                    "updated_at": func.now(),
                },
            )
            .returning(RoutineOverride)
        )
        result = await self._db.execute(stmt)
        return result.scalar_one()

    async def delete_override(self, patient_id: uuid.UUID, override_date: date, anchor: str) -> bool:
        """Withdraw one override. Returns False when there was nothing to
        withdraw, so the caller can answer 404 rather than dispatching a
        reschedule run that would change nothing.

        A hard delete, not a status flag: the row's whole purpose is to feed
        expand_schedule, and once withdrawn it should leave no trace that
        could be read back as history for the clarifying-question suggestion.
        """
        result = await self._db.execute(
            delete(RoutineOverride).where(
                RoutineOverride.patient_id == patient_id,
                RoutineOverride.override_date == override_date,
                RoutineOverride.anchor == anchor,
            )
        )
        return bool(result.rowcount)

    async def mark_overrides_rejected(self, run_id: uuid.UUID) -> None:
        """Retire every override the given run consumed, after that run ended
        NEEDS_REVIEW. Without this the offending row stays ACTIVE and a later
        unrelated reschedule can apply it with no trace that it was once
        refused."""
        await self._db.execute(
            update(RoutineOverride)
            .where(RoutineOverride.consumed_by_run_id == run_id, RoutineOverride.status == "ACTIVE")
            .values(status="REJECTED")
        )

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

    async def mark_overdue_pending_as_missed(
        self, cutoff: datetime
    ) -> list[tuple[uuid.UUID, uuid.UUID, datetime, bool]]:
        """Flip every ScheduledDose still PENDING with current_scheduled_at <
        cutoff to MISSED, across all patients in one statement — regardless
        of is_critical. This is the state-machine half of the scan (a dose
        left PENDING forever would stay retroactively actionable); only the
        streak-alert half below is narrowed to critical doses. Rides
        idx_scheduled_doses_pending_due (current_scheduled_at) WHERE
        status='PENDING'. Race-safe against a patient actioning the same dose
        concurrently: standard row-level UPDATE locking means a row already
        flipped to TAKEN/SKIPPED a moment earlier no longer matches
        status='PENDING' by the time this runs, so it's simply excluded — no
        read-then-write window. Returns (patient_id, dose_id,
        current_scheduled_at, is_critical) for every row just flipped, so the
        caller can pick out which patients had a critical dose newly missed
        this tick without a second query."""
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
                ScheduledDose.is_critical,
            )
        )
        result = await self._db.execute(stmt)
        return [(row[0], row[1], row[2], row[3]) for row in result.all()]

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

    async def get_recent_critical_dose_statuses(
        self, patient_ids: list[uuid.UUID], lookback: int, before: datetime
    ) -> dict[uuid.UUID, list[dict[str, str]]]:
        """Same shape and ROW_NUMBER() OVER (PARTITION BY patient_id ...)
        approach as get_recent_dose_statuses (one query for every affected
        patient, never one per patient), filtered to WHERE is_critical.

        Deliberate semantic difference from the unfiltered version: a patient
        who takes their statin on time but misses their warfarin no longer
        has that on-time statin dose interrupt the streak, because the
        statin dose is excluded from this sequence entirely rather than
        counted as a non-missed entry. The filtered streak is more sensitive
        to critical-only misses, not less — see
        docs/graded-adherence-implementation.md Stage 2. Rides
        idx_scheduled_doses_critical_patient_time (patient_id,
        current_scheduled_at DESC) WHERE is_critical."""
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
                ScheduledDose.is_critical,
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

    async def get_due_dose_groups(self, cutoff: datetime) -> dict[tuple[uuid.UUID, datetime], list[dict[str, Any]]]:
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
        grouped: dict[tuple[uuid.UUID, datetime], list[dict[str, Any]]] = {}
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
