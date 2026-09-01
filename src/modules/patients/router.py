import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_current_user_payload, get_db, require_roles
from src.common.http import get_client_ip
from src.core.response import success_response
from src.modules.admin.repository import AuditLogRepository, DoctorRepository
from src.modules.admin.service import AdminService
from src.modules.auth.repository import AuthRepository
from src.modules.auth.schemas import MessageResponse
from src.modules.patients.repository import PatientRepository
from src.modules.patients.schemas import (
    CreatePatientByDoctorRequest,
    PatientOnboardingRequest,
    UpdateRoutineRequest,
)
from src.modules.patients.service import PatientService


def get_patient_service(db: Annotated[AsyncSession, Depends(get_db)]) -> PatientService:
    """Dependency factory providing PatientService instance."""
    return PatientService(
        db=db,
        patient_repository=PatientRepository(db),
        doctor_repository=DoctorRepository(db),
        audit_repository=AuditLogRepository(db),
        auth_repository=AuthRepository(db),
    )


def get_admin_service(db: Annotated[AsyncSession, Depends(get_db)]) -> AdminService:
    """AdminService dùng lại ở đây chỉ để đọc hồ sơ doctor (GET /doctors/me).

    Hồ sơ doctor thuộc module admin, nhưng endpoint self-service phải nằm dưới
    prefix /doctors — bác sĩ không có quyền vào /admin/*.
    """
    return AdminService(
        db=db,
        doctor_repository=DoctorRepository(db),
        audit_repository=AuditLogRepository(db),
        auth_repository=AuthRepository(db),
    )


PatientServiceDep = Annotated[PatientService, Depends(get_patient_service)]
AdminServiceDep = Annotated[AdminService, Depends(get_admin_service)]
DoctorUserDep = Annotated[dict, Depends(require_roles("DOCTOR"))]
DoctorOrAdminUserDep = Annotated[dict, Depends(require_roles("DOCTOR", "ADMIN"))]
PatientOnlyUserDep = Annotated[dict, Depends(require_roles("PATIENT"))]
# Routine-read access is role-agnostic (self / doctor-prescribed / active-caregiver
# are independent facts checked in the service layer) -- any authenticated user
# may call this; out-of-scope callers still get 404 from the service.
AnyAuthUserDep = Annotated[dict, Depends(get_current_user_payload)]
PatientOrAdminUserDep = Annotated[dict, Depends(require_roles("PATIENT", "ADMIN"))]

router = APIRouter(prefix="/doctors", tags=["Doctor & Patient Clinical Management"])


@router.post("/patients", status_code=status.HTTP_201_CREATED)
async def create_patient(
    request_body: CreatePatientByDoctorRequest,
    raw_request: Request,
    current_user: DoctorUserDep,
    service: PatientServiceDep,
) -> JSONResponse:
    """Create a new Patient account and profile under the requesting Doctor (Doctor only)."""
    ip_address = get_client_ip(raw_request)
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


@router.get("/me")
async def get_my_doctor_profile(
    current_user: DoctorUserDep,
    service: AdminServiceDep,
) -> JSONResponse:
    """Hồ sơ của chính bác sĩ đang đăng nhập.

    Lấy user id từ token chứ không nhận từ client — endpoint này không được
    dùng để đọc hồ sơ của bác sĩ khác (việc đó thuộc GET /admin/doctors/{id}).
    """
    result = await service.get_doctor(doctor_id=uuid.UUID(current_user["sub"]))
    return success_response(
        data=result.model_dump(mode="json"),
        message="Doctor profile fetched successfully",
    )


@router.get("/patients/by-phone")
async def get_patient_by_phone(
    current_user: DoctorUserDep,
    service: PatientServiceDep,
    phone: str = Query(..., pattern=r"^\+?[0-9]{9,15}$", description="Patient phone number"),
) -> JSONResponse:
    """Fetch specific patient profile globally by phone number (Doctor only)."""
    result = await service.get_patient_by_phone(phone=phone)
    return success_response(
        data=result.model_dump(mode="json"),
        message="Patient details fetched successfully",
    )


@router.get("/patients")
async def list_patients(
    current_user: DoctorUserDep,
    service: PatientServiceDep,
    page: int = Query(1, ge=1, le=1000, description="Page number"),
    size: int = Query(10, ge=1, le=100, description="Items per page"),
    search: str | None = Query(None, min_length=2, description="Search by name or phone"),
) -> JSONResponse:
    """Query paginated patient list, restricted to patients the requesting doctor
    has written at least one prescription for (Doctor only)."""
    result = await service.list_patients(actor_payload=current_user, page=page, size=size, search=search)
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


self_router = APIRouter(prefix="/patients", tags=["Patient Profile, Routine & Caregiver Links"])


@self_router.post("/me/profile")
async def onboard_patient(
    request_body: PatientOnboardingRequest,
    current_user: PatientOnlyUserDep,
    service: PatientServiceDep,
) -> JSONResponse:
    """Patient self-onboarding: fills in profile details and sets the initial
    daily routine on first login (Patient only, self via token)."""
    result = await service.onboard_patient(request=request_body, actor_payload=current_user)
    return success_response(
        data=result.model_dump(mode="json"),
        message="Onboarding completed successfully",
    )


@self_router.get("/me/profile")
async def get_self_profile(
    current_user: PatientOnlyUserDep,
    service: PatientServiceDep,
) -> JSONResponse:
    """Fetch the authenticated patient's profile and routine.

    Chat Agent tools use this self-scoped route to read dob/sex for respectful
    Vietnamese address selection without touching doctor-only patient routes.
    """
    result = await service.get_self_profile(actor_payload=current_user)
    return success_response(
        data=result.model_dump(mode="json"),
        message="Patient profile fetched successfully",
    )


@self_router.get("/{patient_id}/routine")
async def get_routine(
    patient_id: uuid.UUID,
    current_user: AnyAuthUserDep,
    service: PatientServiceDep,
) -> JSONResponse:
    """Fetch a patient's daily routine. Access is role-agnostic: self-owned,
    doctor-prescribed, or active-caregiver-linked — checked as independent
    facts, so one account can qualify through more than one."""
    result = await service.get_routine(patient_id=patient_id, actor_payload=current_user)
    return success_response(
        data=result.model_dump(mode="json"),
        message="Routine fetched successfully",
    )


@self_router.put("/{patient_id}/routine")
async def update_routine(
    patient_id: uuid.UUID,
    request_body: UpdateRoutineRequest,
    current_user: PatientOnlyUserDep,
    service: PatientServiceDep,
) -> JSONResponse:
    """Create or update a patient's daily routine (Patient only, self)."""
    result = await service.update_routine(patient_id=patient_id, request=request_body, actor_payload=current_user)
    return success_response(
        data=result.model_dump(mode="json"),
        message="Routine updated successfully",
    )
