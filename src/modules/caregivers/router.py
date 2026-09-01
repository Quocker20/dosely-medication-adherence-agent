import uuid
from typing import Annotated, List

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_db, require_roles
from src.common.http import get_client_ip
from src.core.response import success_response
from src.core.telegram import TelegramClient, get_telegram_client
from src.modules.auth.schemas import MessageResponse
from src.modules.caregivers.schemas import CaregiverLinkDetailResponse, CreateCaregiverLinkRequest
from src.modules.caregivers.service import CaregiverService

router = APIRouter(prefix="/patients", tags=["Caregivers"])

PatientOnlyUserDep = Annotated[dict, Depends(require_roles("PATIENT"))]
PatientOrAdminUserDep = Annotated[dict, Depends(require_roles("PATIENT", "ADMIN"))]


def get_caregiver_service(
    db: Annotated[AsyncSession, Depends(get_db)],
    telegram_client: Annotated[TelegramClient, Depends(get_telegram_client)],
) -> CaregiverService:
    return CaregiverService(db, telegram_client=telegram_client)


CaregiverServiceDep = Annotated[CaregiverService, Depends(get_caregiver_service)]


@router.post("/{patient_id}/caregivers", status_code=status.HTTP_201_CREATED)
async def create_caregiver_link(
    patient_id: uuid.UUID,
    request_body: CreateCaregiverLinkRequest,
    raw_request: Request,
    current_user: PatientOnlyUserDep,
    service: CaregiverServiceDep,
) -> JSONResponse:
    """Link a Caregiver phone to the patient, generating a 6-character link code
    and Telegram deep link (Patient only, self).
    """
    ip_address = get_client_ip(raw_request)
    result = await service.create_caregiver_link(
        patient_id=patient_id,
        request=request_body,
        actor_payload=current_user,
        ip_address=ip_address,
    )
    return success_response(
        data=result.model_dump(mode="json"),
        message="Caregiver linked successfully",
        code=status.HTTP_201_CREATED,
    )


@router.get("/{patient_id}/caregivers")
async def list_caregiver_links(
    patient_id: uuid.UUID,
    current_user: PatientOrAdminUserDep,
    service: CaregiverServiceDep,
) -> JSONResponse:
    """List caregiver links for a patient (Patient self-only, or Admin)."""
    result = await service.list_caregiver_links(patient_id=patient_id, actor_payload=current_user)
    return success_response(
        data=[item.model_dump(mode="json") for item in result],
        message="Caregiver links fetched successfully",
    )


@router.delete("/{patient_id}/caregivers/{caregiver_link_id}")
async def delete_caregiver_link(
    patient_id: uuid.UUID,
    caregiver_link_id: uuid.UUID,
    raw_request: Request,
    current_user: PatientOrAdminUserDep,
    service: CaregiverServiceDep,
) -> JSONResponse:
    """Remove a caregiver link (Patient self-only, or Admin). Hard delete."""
    ip_address = get_client_ip(raw_request)
    await service.delete_caregiver_link(
        patient_id=patient_id,
        caregiver_link_id=caregiver_link_id,
        actor_payload=current_user,
        ip_address=ip_address,
    )
    return success_response(
        data=MessageResponse(message="Caregiver link removed successfully").model_dump(mode="json"),
        message="Caregiver link removed successfully",
    )
