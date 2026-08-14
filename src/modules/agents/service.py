import base64
import logging
import time as time_module
import uuid
from datetime import date, datetime, time, timedelta
from datetime import timezone as dt_timezone
from typing import Optional
from zoneinfo import ZoneInfo

from fastapi import status
from langchain_core.messages import HumanMessage
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.agents.audit import log_turn
from src.agents.graph import agent
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
from src.modules.agents.planner import (
    PlannableItem,
    RoutineTimes,
    expand_schedule,
    validate_frequency_guardrails,
)
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
from src.modules.adherence.repository import AlertRepository
from src.modules.patients.repository import PatientRepository
from src.modules.planning.core.speech import (
    SpeechServiceError,
    synthesize_speech,
    transcribe_audio,
)

logger = logging.getLogger(__name__)

_GRAPH_VERSION = "slice6-v1"
_GENERATE_TASK_NAME = "agents.generate_schedule"


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
        patient_repository: Optional[PatientRepository] = None,
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
        patient_row = await self._patient_repo.get_patient_with_user(
            patient_id, requesting_doctor_id=doctor_id
        )
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
            raise ConflictException(
                message="An agent run is already in progress for this patient"
            )

        self._dispatch_generate(run.id, patient_id, is_reschedule=False)
        return AgentRunAsyncResponse(
            agent_run_id=run.id, status="RUNNING", message="Schedule generation started"
        )

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
            raise ConflictException(
                message="An agent run is already in progress for this patient"
            )

        self._dispatch_generate(run.id, patient_id, is_reschedule=True)
        return AgentRunAsyncResponse(
            agent_run_id=run.id, status="RUNNING", message="Reschedule started"
        )

    async def get_schedule(
        self, patient_id: uuid.UUID, actor_payload: dict, target_date: date
    ) -> ActiveScheduleResponse:
        """PATIENT/DOCTOR/CAREGIVER, role-agnostic access (self-owned,
        doctor-prescribed, or active-caregiver-linked). No access -> empty
        page, list-style filtering (matches PrescriptionService.list_prescriptions),
        not a 404 — avoids leaking which patient UUIDs exist."""
        actor_id = uuid.UUID(actor_payload["sub"])

        patient_timezone = await self._dose_repo.get_patient_timezone_scoped(
            patient_id, actor_id
        )
        if patient_timezone is None:
            return ActiveScheduleResponse(patient_id=patient_id, date=target_date, doses=[])

        tz = ZoneInfo(patient_timezone)
        range_start = datetime.combine(target_date, time.min, tzinfo=tz).astimezone(
            dt_timezone.utc
        )
        range_end = datetime.combine(
            target_date + timedelta(days=1), time.min, tzinfo=tz
        ).astimezone(dt_timezone.utc)

        rows = await self._dose_repo.get_schedule_in_range(
            patient_id, range_start, range_end, actor_id=actor_id
        )
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
                "status": dose.status,
                "snooze_count": dose.snooze_count,
            }
            for dose, display_name in rows
        ]
        return ActiveScheduleResponse(patient_id=patient_id, date=target_date, doses=doses)

    async def get_run_status(
        self, agent_run_id: uuid.UUID, actor_payload: dict
    ) -> AgentRunStatusResponse:
        """PATIENT/DOCTOR/ADMIN, mirrors PrescriptionService.get_prescription's
        actor_id=None-for-ADMIN pattern."""
        role = actor_payload.get("role")
        actor_id = None if role == "ADMIN" else uuid.UUID(actor_payload["sub"])

        run = await self._agent_run_repo.get_by_id(agent_run_id, actor_id=actor_id)
        if run is None:
            raise NotFoundException(message="Agent run not found")
        return AgentRunStatusResponse.model_validate(run)

    async def execute_run(
        self, run_id: uuid.UUID, patient_id: uuid.UUID, is_reschedule: bool
    ) -> None:
        """Worker-facing entrypoint (see tasks.py): no actor scoping, the
        run/patient were already validated when the HTTP request created the
        RUNNING row. Deterministic dose expansion only — no LLM call."""
        settings = get_settings()
        started = time_module.perf_counter()
        try:
            async with self._db.begin():
                if is_reschedule:
                    await self._dose_repo.delete_future_pending(
                        patient_id, now=datetime.now(dt_timezone.utc)
                    )

                patient_timezone, routine = await self._dose_repo.get_patient_context_unscoped(
                    patient_id
                )
                if patient_timezone is None:
                    raise NotFoundException(message="Patient not found")

                item_pairs = await self._dose_repo.get_approved_items(patient_id)
                plannable_items = [
                    PlannableItem(
                        id=item.id,
                        medication_id=item.medication_id,
                        dose_unit=item.dose_unit,
                        morning_dose=item.morning_dose,
                        noon_dose=item.noon_dose,
                        evening_dose=item.evening_dose,
                        bedtime_dose=item.bedtime_dose,
                        meal_relation=item.meal_relation,
                        minimum_interval_minutes=item.minimum_interval_minutes,
                        start_date=item.start_date,
                        end_date=item.end_date,
                    )
                    for item, _prescription_id in item_pairs
                ]
                validate_frequency_guardrails(plannable_items, settings.max_frequency_per_day)
                routine_times = RoutineTimes(
                    wake=routine.wake_time if routine else None,
                    breakfast=routine.breakfast_time if routine else None,
                    lunch=routine.lunch_time if routine else None,
                    dinner=routine.dinner_time if routine else None,
                    sleep=routine.sleep_time if routine else None,
                )
                today_local = datetime.now(ZoneInfo(patient_timezone)).date()

                rows = expand_schedule(
                    plannable_items,
                    routine_times,
                    patient_timezone,
                    today=today_local,
                    horizon_days=settings.schedule_horizon_days,
                    default_min_gap_minutes=settings.min_dose_gap_minutes,
                    max_treatment_days=settings.max_treatment_days,
                )
                row_dicts = [
                    {
                        "prescription_item_id": row.prescription_item_id,
                        "medication_id": row.medication_id,
                        "dose_slot": row.dose_slot,
                        "dose_value": row.dose_value,
                        "dose_unit": row.dose_unit,
                        "meal_relation": row.meal_relation,
                        "patient_id": patient_id,
                        "original_scheduled_at": row.original_scheduled_at,
                        "current_scheduled_at": row.current_scheduled_at,
                        "status": row.status,
                        "snooze_count": row.snooze_count,
                    }
                    for row in rows
                ]
                inserted_count = await self._dose_repo.bulk_insert_doses(row_dicts)

                latency_ms = int((time_module.perf_counter() - started) * 1000)
                await self._agent_run_repo.mark_completed(run_id, latency_ms, inserted_count)
        except Exception as exc:
            logger.exception("Agent run %s failed", run_id)
            latency_ms = int((time_module.perf_counter() - started) * 1000)
            # Prior block's exception already rolled back this session's
            # transaction; begin() below opens a fresh one to persist the
            # failure so it is still observable via GET /agent-runs/{id}.
            async with self._db.begin():
                await self._agent_run_repo.mark_failed(
                    run_id, latency_ms, error_code=type(exc).__name__[:100]
                )


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
        now = datetime.now(dt_timezone.utc)
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
            streaks = await self._dose_repo.get_recent_dose_statuses(
                patient_ids, lookback=threshold, before=now
            )

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

    async def handle_voice_chat(
        self, audio_bytes: bytes, filename: str, patient_id: str
    ) -> VoiceChatResponse:
        try:
            transcript = await transcribe_audio(audio_bytes, filename=filename)
        except SpeechServiceError as e:
            raise AppException(
                message=str(e), code=status.HTTP_502_BAD_GATEWAY
            ) from e

        if not transcript:
            raise ValidationException(
                message="Không nhận được nội dung giọng nói, vui lòng nói lại."
            )

        response_text = await self._run_agent(transcript, patient_id)

        audio_base64 = None
        try:
            audio_reply = await synthesize_speech(response_text)
            audio_base64 = base64.b64encode(audio_reply).decode("ascii")
        except SpeechServiceError:
            # fail-open: a broken TTS vendor must not cost the patient the
            # text answer they already have.
            logger.warning("TTS failed, returning text-only reply")

        return VoiceChatResponse(
            transcript=transcript, response=response_text, audio_base64=audio_base64
        )

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
