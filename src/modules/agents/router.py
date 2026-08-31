import uuid
from datetime import date, datetime
from typing import Annotated, Optional
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_db, oauth2_scheme, require_roles
from src.core.config import get_settings
from src.core.rate_limit import rate_limit_by_user
from src.core.response import success_response
from src.core.security import create_access_token, reset_actor_token, set_actor_token
from src.modules.agents.repository import AgentRunRepository, ChatMemoryRepository, ScheduledDoseRepository
from src.modules.agents.schemas import ChatRequest, GenerateScheduleRequest, RescheduleRequest
from src.modules.agents.service import ChatService, SchedulingService
from src.modules.patients.repository import PatientRepository


def get_scheduling_service(db: Annotated[AsyncSession, Depends(get_db)]) -> SchedulingService:
    """Dependency factory providing SchedulingService instance."""
    return SchedulingService(
        db=db,
        agent_run_repository=AgentRunRepository(db),
        scheduled_dose_repository=ScheduledDoseRepository(db),
        patient_repository=PatientRepository(db),
    )


def get_chat_service(db: Annotated[AsyncSession, Depends(get_db)]) -> ChatService:
    """Dependency factory providing ChatService instance."""
    if get_settings().app_env == "test":
        return ChatService()
    return ChatService(db, ChatMemoryRepository(db))


SchedulingServiceDep = Annotated[SchedulingService, Depends(get_scheduling_service)]
ChatServiceDep = Annotated[ChatService, Depends(get_chat_service)]
DoctorUserDep = Annotated[dict, Depends(require_roles("DOCTOR"))]
PatientUserDep = Annotated[dict, Depends(require_roles("PATIENT"))]
ScheduleReaderDep = Annotated[dict, Depends(require_roles("PATIENT", "DOCTOR", "CAREGIVER"))]
RunReaderDep = Annotated[dict, Depends(require_roles("PATIENT", "DOCTOR", "ADMIN"))]
RawTokenDep = Annotated[Optional[str], Depends(oauth2_scheme)]

schedules_router = APIRouter(tags=["Schedules & AI Agents"])
agent_runs_router = APIRouter(tags=["Schedules & AI Agents"])
chat_router = APIRouter(tags=["Schedules & AI Agents"])


@chat_router.post("/dev/chat", include_in_schema=False)
async def local_dev_chat(request_body: ChatRequest, request: Request, service: ChatServiceDep) -> JSONResponse:
    """No-login test endpoint: explicit dev flag + loopback + fixed patient only."""
    settings = get_settings()
    client_host = request.client.host if request.client else ""
    if settings.app_env != "development" or not settings.enable_local_chat_test:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Not found")
    if client_host not in {"127.0.0.1", "::1", "localhost", "testclient"}:
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="Local chat test is loopback-only")
    browser_origin = request.headers.get("origin") or request.headers.get("referer")
    if browser_origin and (urlparse(browser_origin).hostname or "") not in {"127.0.0.1", "localhost", "::1", "testserver"}:
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="Local chat test rejects non-loopback browser origins")
    try:
        patient_id = str(uuid.UUID(settings.dev_chat_patient_id))
    except ValueError:
        from fastapi import HTTPException
        raise HTTPException(status_code=503, detail="DEV_CHAT_PATIENT_ID is not configured")
    token = create_access_token(user_id=patient_id, role="PATIENT", phone_number="local-test")
    handle = set_actor_token(token)
    try:
        result = await service.handle_text_chat(
            message=request_body.message, patient_id=patient_id,
            client_date=request_body.client_date, client_datetime=request_body.client_datetime,
            conversation_id=request_body.conversation_id,
        )
    finally:
        reset_actor_token(handle)
    return success_response(data=result.model_dump(mode="json"), message="Local chat test reply generated")


@schedules_router.post(
    "/patients/{patient_id}/schedules/generate",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(rate_limit_by_user("schedule", 10, 60))],
)
async def generate_schedule(
    patient_id: uuid.UUID,
    request_body: GenerateScheduleRequest,
    current_user: DoctorUserDep,
    service: SchedulingServiceDep,
) -> JSONResponse:
    """Trigger the Planning Agent for a patient (Doctor only, scoped to a
    doctor who has prescribed for this patient). Deterministic dose
    expansion runs async on a Celery worker; poll GET /agent-runs/{id}."""
    result = await service.request_generation(patient_id=patient_id, request=request_body, actor_payload=current_user)
    return success_response(
        data=result.model_dump(mode="json"),
        message="Schedule generation started",
        code=status.HTTP_202_ACCEPTED,
    )


@schedules_router.get("/patients/{patient_id}/schedules")
async def get_schedule(
    patient_id: uuid.UUID,
    current_user: ScheduleReaderDep,
    service: SchedulingServiceDep,
    target_date: Optional[date] = Query(None, alias="date"),
) -> JSONResponse:
    """Fetch a patient's doses for one local calendar date (defaults to
    today). Access is role-agnostic: self-owned, doctor-prescribed, or
    active-caregiver-linked — out-of-scope returns an empty list, not 404."""
    result = await service.get_schedule(
        patient_id=patient_id,
        actor_payload=current_user,
        target_date=target_date or date.today(),
    )
    return success_response(
        data=result.model_dump(mode="json"),
        message="Schedule fetched successfully",
    )


@schedules_router.get("/patients/me/schedules/next")
async def get_my_next_dose(
    current_user: PatientUserDep,
    service: SchedulingServiceDep,
) -> JSONResponse:
    """Return the authenticated patient's next dose; no caller-supplied patient id."""
    patient_id = uuid.UUID(current_user["sub"])
    result = await service.get_next_dose_for_patient(
        patient_id=patient_id, actor_payload=current_user
    )
    return success_response(
        data=result.model_dump(mode="json"),
        message="Next dose state fetched successfully",
    )


@schedules_router.get("/patients/me/schedules/today")
async def get_my_today_schedule(
    current_user: PatientUserDep,
    service: SchedulingServiceDep,
) -> JSONResponse:
    """Return a fresh DB view of today's schedule for the authenticated patient."""
    patient_id = uuid.UUID(current_user["sub"])
    result = await service.get_today_schedule_for_patient(
        patient_id=patient_id, actor_payload=current_user
    )
    return success_response(
        data=result.model_dump(mode="json"),
        message="Today's schedule fetched successfully",
    )


@schedules_router.post(
    "/patients/{patient_id}/schedules/reschedule",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(rate_limit_by_user("schedule", 10, 60))],
)
async def reschedule_schedule(
    patient_id: uuid.UUID,
    request_body: RescheduleRequest,
    current_user: PatientUserDep,
    service: SchedulingServiceDep,
) -> JSONResponse:
    """Trigger the Rescheduling Agent (Patient only, self-service). Wipes
    future PENDING doses and regenerates from the current routine; past and
    already-actioned doses are untouched."""
    result = await service.request_reschedule(patient_id=patient_id, request=request_body, actor_payload=current_user)
    return success_response(
        data=result.model_dump(mode="json"),
        message="Reschedule started",
        code=status.HTTP_202_ACCEPTED,
    )


@agent_runs_router.get("/agent-runs/{agent_run_id}")
async def get_agent_run_status(
    agent_run_id: uuid.UUID,
    current_user: RunReaderDep,
    service: SchedulingServiceDep,
) -> JSONResponse:
    """Poll an agent run's status/result (Patient/Doctor/Admin)."""
    result = await service.get_run_status(agent_run_id=agent_run_id, actor_payload=current_user)
    return success_response(
        data=result.model_dump(mode="json"),
        message="Agent run status fetched successfully",
    )


# --------------------------------------------------------------------------
# Patient Chat AI (FR-3.2, Voice/Text)
# --------------------------------------------------------------------------
# patient_id comes from the access token's `sub`, never from the request — the
# agent's tools can write dose actions and raise alerts, so a caller-supplied id
# would be a direct write path into another patient's record.
#
# The raw bearer token is bound to the context for the duration of the turn so
# the agent's own HTTP tool calls travel as this patient (see
# src/core/security.py). set/reset is paired in try/finally: leaving a token
# bound would hand it to whatever runs next on this task.


@chat_router.post(
    "/chat",
    dependencies=[Depends(rate_limit_by_user("chat", 20, 60))],
)
async def chat(
    request_body: ChatRequest,
    current_user: PatientUserDep,
    service: ChatServiceDep,
    token: RawTokenDep,
) -> JSONResponse:
    """Chat với AI agent bằng chữ (Patient only, self)."""
    handle = set_actor_token(token)
    try:
        result = await service.handle_text_chat(
            message=request_body.message,
            patient_id=current_user["sub"],
            client_date=request_body.client_date,
            client_datetime=request_body.client_datetime,
            conversation_id=request_body.conversation_id,
        )
    finally:
        reset_actor_token(handle)
    return success_response(
        data=result.model_dump(mode="json"),
        message="Chat reply generated successfully",
    )


@chat_router.get("/chat/{conversation_id}")
async def chat_history(
    conversation_id: uuid.UUID,
    current_user: PatientUserDep,
    service: ChatServiceDep,
) -> JSONResponse:
    """Load a patient's durable conversation history after app reopen."""
    if service._memory is None or service._db is None:
        return success_response(data={"conversationId": str(conversation_id), "messages": []}, message="Chat history loaded")
    try:
        async with service._db.begin():
            rows = await service._memory.get_history(uuid.UUID(str(current_user["sub"])), conversation_id)
    except PermissionError as exc:
        raise HTTPException(status_code=404, detail="Conversation not found") from exc
    return success_response(data={
        "conversationId": str(conversation_id),
        "messages": [
            {"id": str(row.id), "role": row.role, "content": row.content, "createdAt": row.created_at.isoformat()}
            for row in rows
        ],
    }, message="Chat history loaded")


@chat_router.post(
    "/chat/voice",
    dependencies=[Depends(rate_limit_by_user("chat", 20, 60))],
)
async def chat_voice(
    current_user: PatientUserDep,
    service: ChatServiceDep,
    token: RawTokenDep,
    audio: UploadFile = File(...),
    client_date: Optional[date] = Form(None, alias="clientDate"),
    client_datetime: Optional[datetime] = Form(None, alias="clientDateTime"),
    conversation_id: Optional[uuid.UUID] = Form(None, alias="conversationId"),
) -> JSONResponse:
    """Chat bằng giọng nói — cho bệnh nhân cao tuổi không muốn/không tiện gõ chữ."""
    audio_bytes = await audio.read()

    handle = set_actor_token(token)
    try:
        result = await service.handle_voice_chat(
            audio_bytes=audio_bytes,
            filename=audio.filename or "audio.webm",
            patient_id=current_user["sub"],
            client_date=client_date,
            client_datetime=client_datetime,
            conversation_id=conversation_id,
        )
    finally:
        reset_actor_token(handle)
    return success_response(
        data=result.model_dump(mode="json"),
        message="Voice chat reply generated successfully",
    )
