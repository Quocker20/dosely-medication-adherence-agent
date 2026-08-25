import base64
import logging
import time as time_module
import uuid
from datetime import UTC, date, datetime, time, timedelta
from enum import Enum
from zoneinfo import ZoneInfo

from fastapi import status
from langchain_core.messages import HumanMessage
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.agents.audit import log_turn
from src.agents.graph import agent
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
from src.core.celery_app import celery_app
from src.core.config import get_settings
from src.core.redis import publish_dashboard_event
from src.modules.adherence.repository import AlertRepository
from src.modules.agents.grouping import schedule_rows_hmac
from src.modules.agents.planner import PlanningNeedsReviewError
from src.modules.agents.repository import AgentRunRepository, ScheduledDoseRepository
from src.modules.agents.schemas import (
    ActiveScheduleResponse,
    AgentRunAsyncResponse,
    AgentRunStatusResponse,
    ChatResponse,
    GenerateScheduleRequest,
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


class AutoscheduleOutcome(str, Enum):
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
        return ActiveScheduleResponse(patient_id=patient_id, date=target_date, doses=doses)

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
                    claim_token=claim_token,
                    **self._terminal_audit(draft_state, empty_hash, "needs_review"),
                )
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
                    claim_token=claim_token,
                    **self._terminal_audit(draft_state, empty_hash, "failed"),
                )
            return

        await publish_dashboard_event(
            "schedule.updated",
            {
                "patient_id": str(patient_id),
                "agent_run_id": str(run_id),
                "generated_dose_count": inserted_count,
                "is_reschedule": is_reschedule,
            },
        )

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
    token — see safety_tools.py's _send_alert)."""

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

        # Keep each patient's most-recently-missed dose id (for the alert's
        # triggered_by_id / idempotency key) — a single scan can flip several
        # overdue doses per patient at once.
        last_dose_by_patient: dict[uuid.UUID, tuple[uuid.UUID, datetime]] = {}
        for patient_id, dose_id, scheduled_at in affected:
            prev = last_dose_by_patient.get(patient_id)
            if prev is None or scheduled_at > prev[1]:
                last_dose_by_patient[patient_id] = (dose_id, scheduled_at)

        patient_ids = list(last_dose_by_patient)
        async with self._db.begin():
            streaks = await self._dose_repo.get_recent_dose_statuses(patient_ids, lookback=threshold, before=now)

        for patient_id in patient_ids:
            doses = streaks.get(patient_id, [])
            if len(doses) < threshold or count_missed_dose_streak(doses) < threshold:
                continue
            last_dose_id, _ = last_dose_by_patient[patient_id]
            idempotency_key = f"missed-dose-streak:{patient_id}:{last_dose_id}"
            try:
                async with self._db.begin():
                    await self._alert_repo.create_alert(
                        patient_id=patient_id,
                        triggered_by_type=_MISSED_DOSE_TRIGGERED_BY_TYPE,
                        triggered_by_id=last_dose_id,
                        alert_type=_MISSED_DOSE_ALERT_TYPE,
                        severity=_MISSED_DOSE_ALERT_SEVERITY,
                        message=f"{threshold}+ liều liên tiếp bị bỏ lỡ/quá giờ.",
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

    async def handle_text_chat(self, message: str, patient_id: str) -> ChatResponse:
        response_text = await self._run_agent(message, patient_id)
        return ChatResponse(response=response_text)

    async def handle_voice_chat(self, audio_bytes: bytes, filename: str, patient_id: str) -> VoiceChatResponse:
        try:
            transcript = await transcribe_audio(audio_bytes, filename=filename)
        except SpeechServiceError as e:
            raise AppException(message=str(e), code=status.HTTP_502_BAD_GATEWAY) from e

        if not transcript:
            raise ValidationException(message="Không nhận được nội dung giọng nói, vui lòng nói lại.")

        response_text = await self._run_agent(transcript, patient_id)

        audio_base64 = None
        try:
            audio_reply = await synthesize_speech(response_text)
            audio_base64 = base64.b64encode(audio_reply).decode("ascii")
        except SpeechServiceError:
            # fail-open: a broken TTS vendor must not cost the patient the
            # text answer they already have.
            logger.warning("TTS failed, returning text-only reply")

        return VoiceChatResponse(transcript=transcript, response=response_text, audio_base64=audio_base64)

    @staticmethod
    async def _run_agent(message: str, patient_id: str) -> str:
        result = await agent.ainvoke(
            {
                "messages": [HumanMessage(content=message)],
                "patient_id": patient_id,
            }
        )
        response_text = result["messages"][-1].content
        log_turn(
            patient_id=patient_id,
            intent=result.get("intent"),
            escalated=bool(result.get("escalated")),
            response_length=len(response_text),
        )
        return response_text
