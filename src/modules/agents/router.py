import uuid
from datetime import date
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_db, require_roles
from src.core.response import success_response
from src.modules.agents.repository import AgentRunRepository, ScheduledDoseRepository
from src.modules.agents.schemas import GenerateScheduleRequest, RescheduleRequest
from src.modules.agents.service import SchedulingService
from src.modules.patients.repository import PatientRepository


def get_scheduling_service(
    db: Annotated[AsyncSession, Depends(get_db)]
) -> SchedulingService:
    """Dependency factory providing SchedulingService instance."""
    return SchedulingService(
        db=db,
        agent_run_repository=AgentRunRepository(db),
        scheduled_dose_repository=ScheduledDoseRepository(db),
        patient_repository=PatientRepository(db),
    )


SchedulingServiceDep = Annotated[SchedulingService, Depends(get_scheduling_service)]
DoctorUserDep = Annotated[dict, Depends(require_roles("DOCTOR"))]
PatientUserDep = Annotated[dict, Depends(require_roles("PATIENT"))]
ScheduleReaderDep = Annotated[dict, Depends(require_roles("PATIENT", "DOCTOR", "CAREGIVER"))]
RunReaderDep = Annotated[dict, Depends(require_roles("PATIENT", "DOCTOR", "ADMIN"))]

schedules_router = APIRouter(tags=["Schedules & AI Agents"])
agent_runs_router = APIRouter(tags=["Schedules & AI Agents"])


@schedules_router.post(
    "/patients/{patient_id}/schedules/generate", status_code=status.HTTP_202_ACCEPTED
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
    result = await service.request_generation(
        patient_id=patient_id, request=request_body, actor_payload=current_user
    )
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


@schedules_router.post(
    "/patients/{patient_id}/schedules/reschedule", status_code=status.HTTP_202_ACCEPTED
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
    result = await service.request_reschedule(
        patient_id=patient_id, request=request_body, actor_payload=current_user
    )
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
    result = await service.get_run_status(
        agent_run_id=agent_run_id, actor_payload=current_user
    )
    return success_response(
        data=result.model_dump(mode="json"),
        message="Agent run status fetched successfully",
    )


# --------------------------------------------------------------------------
# Patient Chat AI (FR-3.2, Voice/Text)
# --------------------------------------------------------------------------
import base64
from fastapi import File, HTTPException, UploadFile
from langchain_core.messages import HumanMessage
from src.agents.audit import log_turn
from src.agents.graph import agent
from src.agents.schemas import ChatRequest, ChatResponse, VoiceChatResponse
from src.modules.planning.core.speech import SpeechServiceError, synthesize_speech, transcribe_audio

chat_router = APIRouter(tags=["Schedules & AI Agents"])

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

@chat_router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest, current_user: PatientUserDep) -> ChatResponse:
    """Chat với AI agent bằng chữ cho chính bệnh nhân trong access token."""
    patient_id = str(current_user["sub"])
    try:
        response_text = await _run_agent(request.message, patient_id)
        return ChatResponse(response=response_text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@chat_router.post("/chat/voice", response_model=VoiceChatResponse)
async def chat_voice(
    current_user: PatientUserDep,
    audio: UploadFile = File(...),
) -> VoiceChatResponse:
    """Chat giọng nói cho chính bệnh nhân trong access token."""
    patient_id = str(current_user["sub"])
    audio_bytes = await audio.read()

    try:
        transcript = await transcribe_audio(audio_bytes, filename=audio.filename or "audio.webm")
    except SpeechServiceError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e

    if not transcript:
        raise HTTPException(status_code=422, detail="Không nhận được nội dung giọng nói, vui lòng nói lại.")

    try:
        response_text = await _run_agent(transcript, patient_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

    audio_base64 = None
    try:
        audio_reply = await synthesize_speech(response_text)
        audio_base64 = base64.b64encode(audio_reply).decode("ascii")
    except SpeechServiceError:
        pass  # fail-open

    return VoiceChatResponse(transcript=transcript, response=response_text, audio_base64=audio_base64)
