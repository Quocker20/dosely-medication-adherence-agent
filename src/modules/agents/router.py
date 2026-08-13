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
