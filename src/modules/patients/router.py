import uuid
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_db, require_roles
from src.core.response import success_response
from src.modules.admin.repository import AuditLogRepository, DoctorRepository
from src.modules.auth.repository import AuthRepository
from src.modules.patients.repository import PatientRepository
from src.modules.patients.schemas import CreatePatientByDoctorRequest
from src.modules.patients.service import PatientService


def _get_client_ip(request: Request) -> str:
    """Extract client IP address from request headers or host."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "127.0.0.1"


def get_patient_service(db: Annotated[AsyncSession, Depends(get_db)]) -> PatientService:
    """Dependency factory providing PatientService instance."""
    return PatientService(
        db=db,
        patient_repository=PatientRepository(db),
        doctor_repository=DoctorRepository(db),
        audit_repository=AuditLogRepository(db),
        auth_repository=AuthRepository(db),
    )


PatientServiceDep = Annotated[PatientService, Depends(get_patient_service)]
DoctorUserDep = Annotated[dict, Depends(require_roles("DOCTOR"))]
DoctorOrAdminUserDep = Annotated[dict, Depends(require_roles("DOCTOR", "ADMIN"))]

router = APIRouter(prefix="/doctors", tags=["Doctor & Patient Clinical Management"])


@router.post("/patients", status_code=status.HTTP_201_CREATED)
async def create_patient(
    request_body: CreatePatientByDoctorRequest,
    raw_request: Request,
    current_user: DoctorUserDep,
    service: PatientServiceDep,
) -> JSONResponse:
    """Create a new Patient account and profile under the requesting Doctor (Doctor only)."""
    ip_address = _get_client_ip(raw_request)
    result = await service.create_patient(
        request=request_body,
        actor_payload=current_user,
        ip_address=ip_address,
    )
    return success_response(
        data=result.model_dump(mode="json"),
        message="Patient account created successfully",
        code=status.HTTP_201_CREATED,
    )


@router.get("/patients")
async def list_patients(
    current_user: DoctorUserDep,
    service: PatientServiceDep,
    page: int = Query(1, ge=1, le=1000, description="Page number"),
    size: int = Query(10, ge=1, le=100, description="Items per page"),
    search: Optional[str] = Query(None, min_length=2, description="Search by name or phone"),
) -> JSONResponse:
    """Query paginated patient list, restricted to patients the requesting doctor
    has written at least one prescription for (Doctor only)."""
    result = await service.list_patients(
        actor_payload=current_user, page=page, size=size, search=search
    )
    return success_response(
        data=result.model_dump(mode="json"),
        message="Patient list fetched successfully",
    )


@router.get("/patients/{patient_id}")
async def get_patient_detail(
    patient_id: uuid.UUID,
    current_user: DoctorOrAdminUserDep,
    service: PatientServiceDep,
) -> JSONResponse:
    """Fetch specific patient profile by user ID.

    A Doctor may access only patients they have written at least one prescription
    for; Admin is unrestricted. Out-of-scope patients return 404, identical to a
    patient that does not exist.
    """
    result = await service.get_patient(patient_id=patient_id, actor_payload=current_user)
    return success_response(
        data=result.model_dump(mode="json"),
        message="Patient details fetched successfully",
    )
