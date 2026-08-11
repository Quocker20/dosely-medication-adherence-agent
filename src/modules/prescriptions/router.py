import uuid
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_current_user_payload, get_db
from src.core.response import success_response
from src.modules.prescriptions.repository import MedicationRepository
from src.modules.prescriptions.service import MedicationService


def get_medication_service(
    db: Annotated[AsyncSession, Depends(get_db)]
) -> MedicationService:
    """Dependency factory providing MedicationService instance."""
    return MedicationService(db=db, medication_repository=MedicationRepository(db))


MedicationServiceDep = Annotated[MedicationService, Depends(get_medication_service)]
AuthenticatedUserDep = Annotated[dict, Depends(get_current_user_payload)]

router = APIRouter(tags=["Medications"])


@router.get("/medications")
async def list_medications(
    current_user: AuthenticatedUserDep,
    service: MedicationServiceDep,
    page: int = Query(1, ge=1, le=1000, description="Page number"),
    size: int = Query(10, ge=1, le=100, description="Items per page"),
    search: Optional[str] = Query(None, min_length=2, description="Search by name"),
) -> JSONResponse:
    """Query paginated medication catalog (any authenticated role)."""
    result = await service.list_medications(page=page, size=size, search=search)
    return success_response(
        data=result.model_dump(mode="json"),
        message="Medication list fetched successfully",
    )


@router.get("/medications/{medication_id}")
async def get_medication_detail(
    medication_id: uuid.UUID,
    current_user: AuthenticatedUserDep,
    service: MedicationServiceDep,
) -> JSONResponse:
    """Fetch medication detail by ID (any authenticated role)."""
    result = await service.get_medication(medication_id=medication_id)
    return success_response(
        data=result.model_dump(mode="json"),
        message="Medication details fetched successfully",
    )
