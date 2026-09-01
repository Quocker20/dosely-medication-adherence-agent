import base64
import logging
import time as time_module
import uuid
from datetime import UTC, date, datetime, time, timedelta
from enum import StrEnum
from typing import cast
from zoneinfo import ZoneInfo

from fastapi import status
from langchain_core.messages import AIMessage, HumanMessage
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.agents.audit import log_turn
from src.agents.conversation_memory import load_working_memory, save_working_memory
from src.agents.graph import agent
from src.agents.patient_addressing import get_patient_address
from src.agents.patient_presentation import patient_facing_text
from src.agents.planning_graph import (
    planning_commit_graph,
    planning_draft_graph,
    planning_snapshot_graph,
)
from src.agents.tools.safety_tools import count_missed_dose_streak
from src.common.exceptions import (
    AppException,
    ConflictException,
    ForbiddenException,
    NotFoundException,
    ValidationException,
)
from src.core.cache import invalidate_prefix
from src.core.celery_app import celery_app
from src.core.config import get_settings
from src.core.redis import publish_dashboard_event
from src.modules.adherence.repository import AlertRepository
from src.modules.agents.grouping import schedule_rows_hmac
from src.modules.agents.planner import PlanningNeedsReviewError
from src.modules.agents.repository import AgentRunRepository, ChatMemoryRepository, ScheduledDoseRepository
from src.modules.agents.schemas import (
    ActiveScheduleResponse,
    AgentRunAsyncResponse,
    AgentRunStatusResponse,
    CancelRoutineOverrideRequest,
    ChatResponse,
    GenerateScheduleRequest,
    NextDoseResponse,
    RecentRoutineOverrideResponse,
    ReportRoutineDeviationRequest,
    RescheduleRequest,
    VoiceChatResponse,
)
from src.modules.patients.repository import PatientRepository
from src.modules.planning.core.speech import (
    SpeechServiceError,
    synthesize_speech,
    transcribe_audio,
)

logger = logging.getLogger(__name__)

_GRAPH_VERSION = "planning-langgraph-v2"
_GENERATE_TASK_NAME = "agents.generate_schedule"
_ROUTINE_UPDATED_TRIGGER = "ROUTINE_UPDATED"


class AgentRunLeaseBusyError(RuntimeError):
    """A redelivered task arrived before the previous claim expired."""


class AutoscheduleOutcome(StrEnum):
    """Why an automatic planning trigger did or didn't start a run."""

    DISPATCHED = "DISPATCHED"
    NOTHING_TO_PLAN = "NOTHING_TO_PLAN"
    RUN_IN_FLIGHT = "RUN_IN_FLIGHT"


class SchedulingService:
    """Service handling schedule generation/reschedule orchestration and
    AgentRun state. HTTP-facing methods enforce RBAC/access and dispatch a
    Celery task after commit; execute_run is the worker-facing entrypoint
    that does the actual deterministic dose expansion (called from a
    separate DB session/event loop — see tasks.py)."""

    def __init__(
        self,
        db: AsyncSession,
        agent_run_repository: AgentRunRepository,
        scheduled_dose_repository: ScheduledDoseRepository,
        patient_repository: PatientRepository | None = None,
    ) -> None:
        self._db = db
        self._agent_run_repo = agent_run_repository
        self._dose_repo = scheduled_dose_repository
        self._patient_repo = patient_repository or PatientRepository(db)

    @staticmethod
    def _dispatch_generate(run_id: uuid.UUID, patient_id: uuid.UUID, is_reschedule: bool) -> None:
        """Fire the Celery task by name rather than importing tasks.py — the
        worker process registers it separately, and this keeps service.py
        free of a dependency on the Celery task decorator."""
        celery_app.send_task(
            _GENERATE_TASK_NAME,
            args=[str(run_id), str(patient_id), is_reschedule],
        )

    async def request_generation(
        self,
        patient_id: uuid.UUID,
        request: GenerateScheduleRequest,
        actor_payload: dict,
    ) -> AgentRunAsyncResponse:
        """DOCTOR only, scoped to a doctor who has prescribed for this
        patient — mirrors PrescriptionService's doctor-ownership checks."""
        doctor_id = uuid.UUID(actor_payload["sub"])
        patient_row = await self._patient_repo.get_patient_with_user(patient_id, requesting_doctor_id=doctor_id)
        if patient_row is None:
            raise NotFoundException(message="Patient not found")
        if self._db.in_transaction():
            # Autobegin trap (CLAUDE.md): the SELECT above autobegins an
            # implicit transaction on the session; commit() closes it (no
            # writes happened either way) so the explicit begin() below
            # doesn't raise "A transaction is already begun on this Session".
            await self._db.commit()

        try:
            async with self._db.begin():
                run = await self._agent_run_repo.create_run(
                    patient_id=patient_id,
                    agent_type="PLANNING_AGENT",
                    trigger_type="MANUAL",
                    graph_version=_GRAPH_VERSION,
                )
        except IntegrityError:
            raise ConflictException(message="An agent run is already in progress for this patient")

        self._dispatch_generate(run.id, patient_id, is_reschedule=False)
        return AgentRunAsyncResponse(agent_run_id=run.id, status="RUNNING", message="Schedule generation started")

    async def request_reschedule(
        self,
        patient_id: uuid.UUID,
        request: RescheduleRequest,
        actor_payload: dict,
    ) -> AgentRunAsyncResponse:
        """PATIENT only, scoped to their own patient_id."""
        actor_id = uuid.UUID(actor_payload["sub"])
        if actor_id != patient_id:
            raise ForbiddenException(message="Cannot reschedule another patient's plan")

        patient_row = await self._patient_repo.get_patient_with_user(patient_id)
        if patient_row is None:
            raise NotFoundException(message="Patient not found")
        if self._db.in_transaction():
            await self._db.commit()

        try:
            async with self._db.begin():
                run = await self._agent_run_repo.create_run(
                    patient_id=patient_id,
                    agent_type="RESCHEDULING_AGENT",
                    trigger_type="MANUAL",
                    graph_version=_GRAPH_VERSION,
                )
        except IntegrityError:
            raise ConflictException(message="An agent run is already in progress for this patient")

        self._dispatch_generate(run.id, patient_id, is_reschedule=True)
        return AgentRunAsyncResponse(agent_run_id=run.id, status="RUNNING", message="Reschedule started")

    async def report_routine_deviation(
        self,
        patient_id: uuid.UUID,
        request: ReportRoutineDeviationRequest,
        actor_payload: dict,
    ) -> AgentRunAsyncResponse:
        """Single-anchor convenience wrapper over report_routine_deviations."""
        return await self.report_routine_deviations(patient_id, [request], actor_payload)

    async def report_routine_deviations(
        self,
        patient_id: uuid.UUID,
        requests: list[ReportRoutineDeviationRequest],
        actor_payload: dict,
    ) -> AgentRunAsyncResponse:
        """PATIENT only, self-service. Upserts every reported RoutineOverride
        in ONE transaction, then reuses request_reschedule verbatim — no
        duplicated Celery dispatch/AgentRun creation.

        Deliberately batched: uq_agent_runs_one_running permits a single
        in-flight run per patient, so reporting anchors one at a time made the
        second report fail with a 409. An end-of-day survey routinely carries
        more than one deviation, so the batch is the primary path and the
        single-anchor call is the special case.

        The deterministic planner (expand_schedule plus its existing
        validators) still governs: a hard constraint conflict still surfaces
        as NEEDS_REVIEW via the same execute_run path, leaving the active
        schedule untouched.
        """
        if not requests:
            raise ValidationException(message="No routine deviations supplied")

        actor_id = uuid.UUID(actor_payload["sub"])
        if actor_id != patient_id:
            raise ForbiddenException(message="Cannot report a deviation for another patient")

        patient_timezone = await self._dose_repo.get_patient_timezone_scoped(patient_id, actor_id)
        if patient_timezone is None:
            raise NotFoundException(message="Patient not found")
        if self._db.in_transaction():
            await self._db.commit()

        today_local = datetime.now(UTC).astimezone(ZoneInfo(patient_timezone)).date()
        resolved_dates = [self._resolve_override_date(request, today_local) for request in requests]

        # Two times for one anchor on one day contradict each other. The
        # unique constraint would silently keep whichever was applied last,
        # so reject instead of picking one — the planner never guesses.
        keys = list(zip(resolved_dates, [request.anchor for request in requests]))
        if len(set(keys)) != len(keys):
            raise ValidationException(message="Duplicate anchor reported for the same day")

        # The run row and the override rows must land in ONE transaction.
        # _dispatch_generate below is fire-and-forget, so a worker starting
        # between two separate commits would either miss the overrides or, on
        # failure, be unable to find them to mark REJECTED. Creating the run
        # first also means a 409 here leaves no orphaned override behind —
        # previously the override was committed before the run was attempted
        # and survived as an ACTIVE row nothing would ever consume.
        #
        # This is why the batch does not simply call request_reschedule: that
        # method owns its own transaction and cannot enclose the upserts.
        try:
            async with self._db.begin():
                run = await self._agent_run_repo.create_run(
                    patient_id=patient_id,
                    agent_type="RESCHEDULING_AGENT",
                    trigger_type="MANUAL",
                    graph_version=_GRAPH_VERSION,
                )
                for request, override_date in zip(requests, resolved_dates):
                    await self._dose_repo.upsert_override(
                        patient_id,
                        override_date,
                        request.anchor,
                        request.overridden_time,
                        request.source,
                        request.reason,
                        consumed_by_run_id=run.id,
                    )
        except IntegrityError:
            raise ConflictException(message="An agent run is already in progress for this patient")

        self._dispatch_generate(run.id, patient_id, is_reschedule=True)
        return AgentRunAsyncResponse(agent_run_id=run.id, status="RUNNING", message="Reschedule started")

    @staticmethod
    def _resolve_override_date(request: ReportRoutineDeviationRequest, today_local: date) -> date:
        """Settle the target day in the patient's own timezone and bound it.

        The window is [today, today + schedule_horizon_days] for a structural
        reason, not an arbitrary policy one: get_active_overrides is queried
        over exactly that range and expand_schedule only materialises days
        inside it, so an override stored outside the window would never be
        read by anything and would look accepted while doing nothing.
        """
        horizon_days = get_settings().schedule_horizon_days
        if request.day_offset is not None:
            override_date = today_local + timedelta(days=request.day_offset)
        else:
            # Guaranteed non-None by the schema's exactly-one validator.
            override_date = cast(date, request.override_date)

        if override_date < today_local:
            raise ValidationException(message="Routine overrides cannot be applied to a past day")
        if override_date > today_local + timedelta(days=horizon_days):
            raise ValidationException(
                message=f"Routine overrides can only be applied within the next {horizon_days} days"
            )
        return override_date

    async def cancel_routine_override(
        self,
        patient_id: uuid.UUID,
        request: CancelRoutineOverrideRequest,
        actor_payload: dict,
    ) -> AgentRunAsyncResponse:
        """Withdraw a previously reported override and put that day's doses
        back on the permanent routine.

        Like reporting, this only stages data and then hands off to the same
        deterministic pipeline: deleting the row is what makes the next
        expand_schedule fall back to the permanent routine for that day.
        """
        actor_id = uuid.UUID(actor_payload["sub"])
        if actor_id != patient_id:
            raise ForbiddenException(message="Cannot cancel another patient's routine override")

        patient_timezone = await self._dose_repo.get_patient_timezone_scoped(patient_id, actor_id)
        if patient_timezone is None:
            raise NotFoundException(message="Patient not found")
        if self._db.in_transaction():
            await self._db.commit()

        today_local = datetime.now(UTC).astimezone(ZoneInfo(patient_timezone)).date()
        if request.override_date < today_local:
            raise ValidationException(message="Routine overrides cannot be cancelled for a past day")

        try:
            async with self._db.begin():
                run = await self._agent_run_repo.create_run(
                    patient_id=patient_id,
                    agent_type="RESCHEDULING_AGENT",
                    trigger_type="MANUAL",
                    graph_version=_GRAPH_VERSION,
                )
                deleted = await self._dose_repo.delete_override(patient_id, request.override_date, request.anchor)
                if not deleted:
                    raise NotFoundException(message="No routine override to cancel for that day and anchor")
        except IntegrityError:
            raise ConflictException(message="An agent run is already in progress for this patient")

        self._dispatch_generate(run.id, patient_id, is_reschedule=True)
        return AgentRunAsyncResponse(agent_run_id=run.id, status="RUNNING", message="Reschedule started")

    async def get_recent_routine_overrides(
        self, patient_id: uuid.UUID, anchor: str, actor_payload: dict, limit: int = 5
    ) -> list[RecentRoutineOverrideResponse]:
        """PATIENT only, self-service read. Used to phrase a smarter
        clarifying question in chat when a deviation is reported without a
        concrete time — never to auto-apply a time."""
        actor_id = uuid.UUID(actor_payload["sub"])
        if actor_id != patient_id:
            raise ForbiddenException(message="Cannot read another patient's routine overrides")

        patient_timezone = await self._dose_repo.get_patient_timezone_scoped(patient_id, actor_id)
        if patient_timezone is None:
            raise NotFoundException(message="Patient not found")
        today_local = datetime.now(UTC).astimezone(ZoneInfo(patient_timezone)).date()

        rows = await self._dose_repo.get_recent_overrides_for_anchor(patient_id, anchor, today_local, limit=limit)
        return [
            RecentRoutineOverrideResponse(override_date=override_date, overridden_time=overridden_time)
            for override_date, overridden_time in rows
        ]

    async def request_autoschedule(
        self,
        patient_id: uuid.UUID,
        prescription_id: uuid.UUID | None,
        trigger_type: str,
    ) -> AutoscheduleOutcome:
        """Worker-side planning trigger for prescription approval / routine
        change. No actor scoping: authorisation already happened at the HTTP
        layer, on the doctor approving or the patient editing their own
        routine.

        Returns an outcome instead of raising ConflictException the way the
        HTTP entrypoints do — a busy patient means "try again shortly", not a
        409 for a caller that no longer exists.
        """
        is_reschedule = trigger_type == _ROUTINE_UPDATED_TRIGGER

        # Nothing approved means nothing to plan. Bailing out here keeps a
        # patient who edits their routine before ever being prescribed
        # anything from accumulating NEEDS_REVIEW runs that no clinician
        # needs to look at.
        item_pairs = await self._dose_repo.get_approved_items(patient_id)
        if self._db.in_transaction():
            await self._db.commit()
        if not item_pairs:
            logger.info(
                "Skipping %s autoschedule for patient %s: no approved prescription items",
                trigger_type,
                patient_id,
            )
            return AutoscheduleOutcome.NOTHING_TO_PLAN

        try:
            async with self._db.begin():
                run = await self._agent_run_repo.create_run(
                    patient_id=patient_id,
                    agent_type="RESCHEDULING_AGENT" if is_reschedule else "PLANNING_AGENT",
                    trigger_type=trigger_type,
                    graph_version=_GRAPH_VERSION,
                    prescription_id=prescription_id,
                )
        except IntegrityError:
            # uq_agent_runs_one_running. The in-flight run re-reads approved
            # items inside its own commit transaction, so it may well pick this
            # change up on its own — but only if it hasn't committed yet.
            # Retrying is what closes the case where it already has.
            logger.info("Autoschedule for patient %s deferred: a run is in flight", patient_id)
            return AutoscheduleOutcome.RUN_IN_FLIGHT

        self._dispatch_generate(run.id, patient_id, is_reschedule=is_reschedule)
        return AutoscheduleOutcome.DISPATCHED

    async def get_schedule(
        self, patient_id: uuid.UUID, actor_payload: dict, target_date: date
    ) -> ActiveScheduleResponse:
        """PATIENT/DOCTOR/CAREGIVER, role-agnostic access (self-owned,
        doctor-prescribed, or active-caregiver-linked). No access -> empty
        page, list-style filtering (matches PrescriptionService.list_prescriptions),
        not a 404 — avoids leaking which patient UUIDs exist."""
        actor_id = uuid.UUID(actor_payload["sub"])

        patient_timezone = await self._dose_repo.get_patient_timezone_scoped(patient_id, actor_id)
        if patient_timezone is None:
            return ActiveScheduleResponse(patient_id=patient_id, date=target_date, doses=[])

        tz = ZoneInfo(patient_timezone)
        range_start = datetime.combine(target_date, time.min, tzinfo=tz).astimezone(UTC)
        range_end = datetime.combine(target_date + timedelta(days=1), time.min, tzinfo=tz).astimezone(UTC)

        rows = await self._dose_repo.get_schedule_in_range(patient_id, range_start, range_end, actor_id=actor_id)
        doses = [
            {
                "scheduled_dose_id": dose.id,
                "prescription_item_id": dose.prescription_item_id,
                "medication_id": dose.medication_id,
                "medication_name": display_name,
                "current_scheduled_at": dose.current_scheduled_at,
                "dose_slot": dose.dose_slot,
                "dose_value": dose.dose_value,
                "dose_unit": dose.dose_unit,
                "meal_relation": dose.meal_relation,
                "notification_group_id": dose.notification_group_id,
                "status": dose.status,
                "snooze_count": dose.snooze_count,
            }
            for dose, display_name in rows
        ]
        return ActiveScheduleResponse(
            patient_id=patient_id,
            date=target_date,
            timezone=patient_timezone,
            doses=doses,
        )

    async def get_next_dose_for_patient(self, patient_id: uuid.UUID, actor_payload: dict) -> NextDoseResponse:
        """Return a structured next-dose state using the patient's timezone.

        Identity is supplied by the authenticated route, never by chat text.
        NO_SCHEDULE means no dose rows exist today; NO_UPCOMING means rows
        exist but none remain actionable in the future today.
        """
        actor_id = uuid.UUID(actor_payload["sub"])
        patient_timezone = await self._dose_repo.get_patient_timezone_scoped(patient_id, actor_id)
        if patient_timezone is None:
            local_date = datetime.now(UTC).date()
            return NextDoseResponse(status="NO_SCHEDULE", local_date=local_date)

        tz = ZoneInfo(patient_timezone)
        now = datetime.now(UTC)
        local_date = now.astimezone(tz).date()
        range_start = datetime.combine(local_date, time.min, tzinfo=tz).astimezone(UTC)
        range_end = datetime.combine(local_date + timedelta(days=1), time.min, tzinfo=tz).astimezone(UTC)
        rows = await self._dose_repo.get_schedule_in_range(patient_id, range_start, range_end, actor_id=actor_id)
        if not rows:
            return NextDoseResponse(status="NO_SCHEDULE", local_date=local_date, timezone=patient_timezone)

        resolved_statuses = {"TAKEN", "SKIPPED", "MISSED"}
        for dose, display_name in rows:
            if dose.current_scheduled_at >= now and dose.status.upper() not in resolved_statuses:
                return NextDoseResponse(
                    status="UPCOMING",
                    local_date=local_date,
                    timezone=patient_timezone,
                    dose={
                        "scheduled_dose_id": dose.id,
                        "medication_name": display_name,
                        "current_scheduled_at": dose.current_scheduled_at,
                        "dose_value": dose.dose_value,
                        "dose_unit": dose.dose_unit,
                        "meal_relation": dose.meal_relation,
                        "status": dose.status,
                    },
                )
        return NextDoseResponse(status="NO_UPCOMING", local_date=local_date, timezone=patient_timezone)

    async def get_today_schedule_for_patient(
        self, patient_id: uuid.UUID, actor_payload: dict
    ) -> ActiveScheduleResponse:
        """Read today's live schedule using the authenticated patient's timezone.

        The date is deliberately calculated by the backend. Chat clients and the
        LLM must not supply either a patient id or a date for this self-service
        path, which prevents cross-patient reads and server-timezone drift.
        """
        actor_id = uuid.UUID(actor_payload["sub"])
        patient_timezone = await self._dose_repo.get_patient_timezone_scoped(patient_id, actor_id)
        if patient_timezone is None:
            return ActiveScheduleResponse(
                patient_id=patient_id,
                date=datetime.now(UTC).date(),
                timezone=None,
                doses=[],
            )

        local_date = datetime.now(UTC).astimezone(ZoneInfo(patient_timezone)).date()
        return await self.get_schedule(
            patient_id=patient_id,
            actor_payload=actor_payload,
            target_date=local_date,
        )

    async def get_run_status(self, agent_run_id: uuid.UUID, actor_payload: dict) -> AgentRunStatusResponse:
        """PATIENT/DOCTOR/ADMIN, mirrors PrescriptionService.get_prescription's
        actor_id=None-for-ADMIN pattern."""
        role = actor_payload.get("role")
        actor_id = None if role == "ADMIN" else uuid.UUID(actor_payload["sub"])

        run = await self._agent_run_repo.get_by_id(agent_run_id, actor_id=actor_id)
        if run is None:
            raise NotFoundException(message="Agent run not found")
        return AgentRunStatusResponse.model_validate(run)

    async def execute_run(self, run_id: uuid.UUID) -> None:
        """Claim and execute one run using DB-owned patient and agent type."""
        settings = get_settings()
        started = time_module.perf_counter()
        run_now = datetime.now(UTC)
        inserted_count = 0
        draft_state: dict | None = None
        claim_token: uuid.UUID | None = None
        empty_hash = schedule_rows_hmac(
            [],
            settings.jwt_secret_key,
            include_notification_groups=False,
        )
        graph_config = {
            "configurable": {
                "dose_repo": self._dose_repo,
                "settings": settings,
            }
        }
        try:
            # Celery is at-least-once. Only the first delivery can claim this
            # RUNNING row; duplicates and already-terminal runs are safe no-ops.
            async with self._db.begin():
                claimed_run = await self._agent_run_repo.claim_run(
                    run_id,
                    settings.planning_run_lease_seconds,
                )
            if claimed_run is None:
                async with self._db.begin():
                    existing_run = await self._agent_run_repo.get_by_id_unscoped(run_id)
                if existing_run is not None and existing_run.status == "RUNNING":
                    raise AgentRunLeaseBusyError("Agent run lease is still active")
                return
            claim_token = claimed_run.claim_token
            if claim_token is None:
                raise RuntimeError("Claimed agent run has no ownership token")
            patient_id = claimed_run.patient_id
            if claimed_run.agent_type == "PLANNING_AGENT":
                is_reschedule = False
            elif claimed_run.agent_type == "RESCHEDULING_AGENT":
                is_reschedule = True
            else:
                latency_ms = int((time_module.perf_counter() - started) * 1000)
                async with self._db.begin():
                    await self._agent_run_repo.mark_failed(
                        run_id,
                        latency_ms,
                        error_code="UnsupportedAgentType",
                        error_message=f"Agent type không hỗ trợ: {claimed_run.agent_type}",
                        claim_token=claim_token,
                        input_hash=empty_hash,
                        output_hash=empty_hash,
                        candidate_source="failed",
                    )
                return

            initial_state = {
                "run_id": run_id,
                "patient_id": patient_id,
                "is_reschedule": is_reschedule,
                "run_now": run_now,
            }
            # SELECTs autobegin, so snapshot reads get a short explicit
            # transaction that closes before any network-capable LLM call.
            async with self._db.begin():
                snapshot_state = await planning_snapshot_graph.ainvoke(
                    initial_state,
                    config=graph_config,
                )

            draft_state = await planning_draft_graph.ainvoke(
                snapshot_state,
                config=graph_config,
            )

            # Fresh APPROVED inputs, deterministic validation, deletion,
            # persistence and terminal audit share one short transaction.
            async with self._db.begin():
                owns_claim = await self._agent_run_repo.renew_claim(
                    run_id,
                    claim_token,
                    settings.planning_run_lease_seconds,
                )
                if not owns_claim:
                    return
                final_state = await planning_commit_graph.ainvoke(
                    draft_state,
                    config=graph_config,
                )
                inserted_count = final_state["generated_dose_count"]
                latency_ms = int((time_module.perf_counter() - started) * 1000)
                completed = await self._agent_run_repo.mark_completed(
                    run_id,
                    latency_ms,
                    inserted_count,
                    model_version=final_state.get("llm_model_version"),
                    prompt_version=final_state.get("llm_prompt_version"),
                    input_hash=final_state.get("input_hash"),
                    output_hash=final_state.get("output_hash"),
                    candidate_source=final_state.get("candidate_source"),
                    error_code=final_state.get("llm_error"),
                    claim_token=claim_token,
                )
                if not completed:
                    raise RuntimeError("Agent run claim was lost before completion")
        except AgentRunLeaseBusyError:
            raise
        except PlanningNeedsReviewError as exc:
            logger.info("Agent run %s requires clinical review: %s", run_id, type(exc).__name__)
            latency_ms = int((time_module.perf_counter() - started) * 1000)
            async with self._db.begin():
                await self._agent_run_repo.mark_needs_review(
                    run_id,
                    latency_ms,
                    error_code=type(exc).__name__[:100],
                    # Message của planner nêu đích danh item và khoảng cách vi
                    # phạm — bác sĩ cần đúng chỗ này mới biết sửa cái gì.
                    error_message=str(exc) or None,
                    claim_token=claim_token,
                    **self._terminal_audit(draft_state, empty_hash, "needs_review"),
                )
                # Retire whatever routine overrides this run was carrying. The
                # schedule is deliberately left untouched, so leaving them
                # ACTIVE would let a later reschedule apply a change this run
                # already established cannot be scheduled safely.
                await self._dose_repo.mark_overrides_rejected(run_id)
            return
        except Exception as exc:
            logger.exception("Agent run %s failed", run_id)
            latency_ms = int((time_module.perf_counter() - started) * 1000)
            if claim_token is None:
                return
            async with self._db.begin():
                await self._agent_run_repo.mark_failed(
                    run_id,
                    latency_ms,
                    error_code=type(exc).__name__[:100],
                    error_message=str(exc) or None,
                    claim_token=claim_token,
                    **self._terminal_audit(draft_state, empty_hash, "failed"),
                )
            return

        await publish_dashboard_event(
            "schedule.updated",
            {
                "patient_id": str(patient_id),
                # A websocket is only a refresh marker.  Medication names,
                # dose counts, and agent-run metadata stay behind the
                # authenticated REST endpoints that clients re-fetch.
                "updated_at": datetime.now(UTC).isoformat(),
            },
        )
        # New/replaced doses change the denominator behind the cached
        # dashboard adherence_rate for this patient.
        await invalidate_prefix("dash:patients")

    @staticmethod
    def _terminal_audit(draft_state: dict | None, empty_hash: str, terminal_source: str) -> dict:
        """Audit every terminal run without persisting plaintext clinical input."""
        state = draft_state or {}
        return {
            "model_version": state.get("llm_model_version"),
            "prompt_version": state.get("llm_prompt_version"),
            "input_hash": state.get("draft_view_hash", empty_hash),
            "output_hash": empty_hash,
            "candidate_source": terminal_source,
        }


_MISSED_DOSE_TRIGGERED_BY_TYPE = "MISSED_DOSES"
_MISSED_DOSE_ALERT_TYPE = "RED_ALERT"
_MISSED_DOSE_ALERT_SEVERITY = "HIGH"


class MissedDoseScanService:
    """Celery-Beat-driven periodic scan (see tasks.py:scan_missed_doses_task).
    Trigger 1 of the Red Alert safety mechanism (cong_viec.md §4.1) — pure
    code, no LLM. Runs outside any authenticated HTTP request (there is no
    single patient's bearer token for a scan touching every patient), so it
    writes through AlertRepository directly rather than POST /patients/{id}/sos
    (the path chat-detected alerts use, which runs under the caller's own
    token — see safety_tools.py's _send_alert).

    The MISSED-flip half below covers every dose regardless of
    PrescriptionItem.is_critical — that's the state machine keeping
    scheduled_doses accurate, and narrowing it would leave non-critical
    overdue doses PENDING forever, retroactively actionable via
    apply_dose_action_cas. Only the streak-alert half is narrowed to
    critical doses (docs/graded-adherence-implementation.md Stage 2): a
    missed vitamin no longer pages a doctor identically to a missed
    anticoagulant. The general (any-medication) missed-dose-streak alert
    that used to run here is retired — the nightly graded-adherence review
    (Stage 3+) covers non-critical adherence trends instead."""

    def __init__(
        self,
        db: AsyncSession,
        scheduled_dose_repository: ScheduledDoseRepository,
        alert_repository: AlertRepository,
    ) -> None:
        self._db = db
        self._dose_repo = scheduled_dose_repository
        self._alert_repo = alert_repository

    async def run_scan(self) -> None:
        settings = get_settings()
        threshold = settings.missed_dose_alert_threshold
        now = datetime.now(UTC)
        cutoff = now - timedelta(minutes=settings.missed_dose_overdue_minutes)

        async with self._db.begin():
            affected = await self._dose_repo.mark_overdue_pending_as_missed(cutoff)
        if not affected:
            return

        # Keep each patient's most-recently-missed CRITICAL dose id (for the
        # alert's triggered_by_id / idempotency key) — a single scan can flip
        # several overdue doses per patient at once, and a non-critical flip
        # must never become the tracked "last missed dose" for a critical
        # streak alert.
        last_dose_by_patient: dict[uuid.UUID, tuple[uuid.UUID, datetime]] = {}
        for patient_id, dose_id, scheduled_at, is_critical in affected:
            if not is_critical:
                continue
            prev = last_dose_by_patient.get(patient_id)
            if prev is None or scheduled_at > prev[1]:
                last_dose_by_patient[patient_id] = (dose_id, scheduled_at)

        patient_ids = list(last_dose_by_patient)
        if not patient_ids:
            # No critical dose was newly missed this tick for anyone — no
            # patient's critical streak could have changed since the last
            # scan, so there is nothing to recheck.
            return
        async with self._db.begin():
            streaks = await self._dose_repo.get_recent_critical_dose_statuses(
                patient_ids, lookback=threshold, before=now
            )

        for patient_id in patient_ids:
            doses = streaks.get(patient_id, [])
            if len(doses) < threshold or count_missed_dose_streak(doses) < threshold:
                continue
            last_dose_id, last_scheduled_at = last_dose_by_patient[patient_id]
            idempotency_key = f"missed-dose-streak:{patient_id}:{last_dose_id}"
            # A once-daily critical drug means "3+ consecutive" spans several
            # days, not one afternoon — name the span so the message doesn't
            # imply same-day urgency it may not have.
            span_days = max(1, (now.date() - last_scheduled_at.date()).days + 1)
            try:
                async with self._db.begin():
                    await self._alert_repo.create_alert(
                        patient_id=patient_id,
                        triggered_by_type=_MISSED_DOSE_TRIGGERED_BY_TYPE,
                        triggered_by_id=last_dose_id,
                        alert_type=_MISSED_DOSE_ALERT_TYPE,
                        severity=_MISSED_DOSE_ALERT_SEVERITY,
                        message=(
                            f"{threshold}+ liều thuốc quan trọng liên tiếp bị bỏ lỡ/quá giờ "
                            f"(trong {span_days} ngày gần đây)."
                        ),
                        idempotency_key=idempotency_key,
                    )
            except IntegrityError:
                # Idempotent replay: this streak already raised an alert
                # (still OPEN/unresolved) on a prior scan tick.
                logger.info(
                    "Missed-dose alert already exists for patient %s (idempotent replay)",
                    patient_id,
                )


class ChatService:
    """Patient-facing conversational agent (FR-3.2), text and voice.

    Stateless and DB-free: the LangGraph agent reaches persistence through its
    own tools over the backend HTTP API, so this service only orchestrates
    transcribe -> agent -> synthesize and never touches AsyncSession.
    """

    def __init__(self, db: AsyncSession | None = None, memory_repository: ChatMemoryRepository | None = None) -> None:
        self._db = db
        self._memory = memory_repository

    async def handle_text_chat(
        self, message: str, patient_id: str, client_date=None, client_datetime=None, conversation_id=None
    ) -> ChatResponse:
        response_text, conversation_id = await self._run_agent(
            message, patient_id, client_date, client_datetime, conversation_id
        )
        return ChatResponse(response=response_text, conversationId=conversation_id)

    async def handle_voice_chat(
        self,
        audio_bytes: bytes,
        filename: str,
        patient_id: str,
        client_date=None,
        client_datetime=None,
        conversation_id=None,
    ) -> VoiceChatResponse:
        try:
            transcript = await transcribe_audio(audio_bytes, filename=filename)
        except SpeechServiceError as e:
            raise AppException(message=str(e), code=status.HTTP_502_BAD_GATEWAY) from e

        if not transcript:
            raise ValidationException(message="Không nhận được nội dung giọng nói, vui lòng nói lại.")

        response_text, conversation_id = await self._run_agent(
            transcript, patient_id, client_date, client_datetime, conversation_id
        )

        audio_base64 = None
        try:
            audio_reply = await synthesize_speech(response_text)
            audio_base64 = base64.b64encode(audio_reply).decode("ascii")
        except SpeechServiceError:
            # fail-open: a broken TTS vendor must not cost the patient the
            # text answer they already have.
            logger.warning("TTS failed, returning text-only reply")

        return VoiceChatResponse(
            transcript=transcript, response=response_text, audio_base64=audio_base64, conversationId=conversation_id
        )

    async def _run_agent(
        self, message: str, patient_id: str, client_date=None, client_datetime=None, conversation_id=None
    ) -> tuple[str, uuid.UUID]:
        persistence_available = self._db is not None and self._memory is not None
        actual_conv_id: uuid.UUID
        if self._db is not None and self._memory is not None:
            try:
                async with self._db.begin():
                    conversation = await self._memory.get_or_create(uuid.UUID(str(patient_id)), conversation_id)
                    actual_conv_id = conversation.id
                    history_rows = await self._memory.recent_messages(actual_conv_id, limit=10)
            except PermissionError as exc:
                raise ForbiddenException(message=str(exc)) from exc
            except Exception:  # memory outage must not make medication chat unavailable
                logger.warning("Durable chat memory unavailable; using turn-local memory", exc_info=True)
                actual_conv_id = uuid.UUID(str(conversation_id)) if conversation_id else uuid.uuid4()
                history_rows = []
                persistence_available = False
        else:  # isolated unit/eval mode; production DI always supplies persistence
            actual_conv_id = uuid.UUID(str(conversation_id)) if conversation_id else uuid.uuid4()
            history_rows = []
        working = await load_working_memory(str(patient_id), str(actual_conv_id)) if persistence_available else {}
        history = [
            HumanMessage(content=row.content) if row.role == "user" else AIMessage(content=row.content)
            for row in history_rows
        ]
        reference_date = client_date or (client_datetime.date() if client_datetime is not None else date.today())
        patient_address = await get_patient_address(patient_id, reference_date)
        result = await agent.ainvoke(
            {
                "messages": history + [HumanMessage(content=message)],
                "patient_id": patient_id,
                "conversation_id": str(actual_conv_id),
                "patient_address": patient_address,
                "client_date": client_date.isoformat() if client_date else None,
                "client_datetime": client_datetime.isoformat() if client_datetime else None,
                "memory_context": working,
            }
        )
        # Sources and citation ids remain available to the grounding/audit
        # pipeline. They are removed exactly once at the API presentation
        # boundary so no ReAct/tool fallback can leak "[Nguồn N]" to patients.
        response_text = patient_facing_text(result["messages"][-1].content)
        if persistence_available:
            async with self._db.begin():
                await self._memory.append_exchange(actual_conv_id, message, response_text, result.get("intent"))
            await invalidate_prefix("chat:conversations")
        metadata = result.get("metadata") if isinstance(result.get("metadata"), dict) else {}
        if metadata.get("resolved_medication"):
            working["current_medication"] = metadata["resolved_medication"]
        if metadata.get("adverse_event_id"):
            # Redis only keeps a short-lived pointer. Clinical symptom data
            # remains in PostgreSQL and is never copied wholesale into prompts.
            working["last_adverse_event_id"] = metadata["adverse_event_id"]
            working["last_adverse_event_at"] = metadata.get("adverse_event_reported_at")
            working["has_unreviewed_adverse_event"] = metadata.get("adverse_event_review_status") != "REVIEWED"
        if "pending_adverse_event" in metadata:
            working["pending_adverse_event"] = metadata["pending_adverse_event"]
        elif metadata.get("clear_pending_adverse_event"):
            working.pop("pending_adverse_event", None)
        elif result.get("intent") == "report_adverse_event" and working.get("pending_adverse_event"):
            working.pop("pending_adverse_event", None)
        if "pending_schedule_request" in metadata:
            working["pending_schedule_request"] = metadata["pending_schedule_request"]
        elif metadata.get("clear_pending_schedule_request"):
            working.pop("pending_schedule_request", None)
        working["last_intent"] = result.get("intent")
        if persistence_available:
            await save_working_memory(str(patient_id), str(actual_conv_id), working)
        log_turn(
            patient_id=patient_id,
            intent=result.get("intent"),
            escalated=bool(result.get("escalated")),
            response_length=len(response_text),
        )
        return response_text, actual_conv_id
