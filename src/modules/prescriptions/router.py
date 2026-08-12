import uuid
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_current_user_payload, get_db, require_roles
from src.core.response import success_response
from src.modules.admin.repository import AuditLogRepository, DoctorRepository
from src.modules.auth.repository import AuthRepository
from src.modules.auth.schemas import MessageResponse
from src.modules.patients.repository import PatientRepository
from src.modules.prescriptions.repository import MedicationRepository, PrescriptionRepository
from src.modules.prescriptions.schemas import (
    CancelPrescriptionRequest,
    CreatePrescriptionItemRequest,
    CreatePrescriptionRequest,
    UpdatePrescriptionItemRequest,
    UpdatePrescriptionRequest,
)
from src.modules.prescriptions.service import MedicationService, PrescriptionService


def _get_client_ip(request: Request) -> str:
    """Extract client IP address from request headers or host."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "127.0.0.1"


def get_medication_service(
    db: Annotated[AsyncSession, Depends(get_db)]
) -> MedicationService:
    """Dependency factory providing MedicationService instance."""
    return MedicationService(db=db, medication_repository=MedicationRepository(db))


def get_prescription_service(
    db: Annotated[AsyncSession, Depends(get_db)]
) -> PrescriptionService:
    """Dependency factory providing PrescriptionService instance."""
    return PrescriptionService(
        db=db,
        prescription_repository=PrescriptionRepository(db),
        doctor_repository=DoctorRepository(db),
        audit_repository=AuditLogRepository(db),
        auth_repository=AuthRepository(db),
        patient_repository=PatientRepository(db),
    )


MedicationServiceDep = Annotated[MedicationService, Depends(get_medication_service)]
PrescriptionServiceDep = Annotated[PrescriptionService, Depends(get_prescription_service)]
AuthenticatedUserDep = Annotated[dict, Depends(get_current_user_payload)]
DoctorUserDep = Annotated[dict, Depends(require_roles("DOCTOR"))]

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


prescriptions_router = APIRouter(tags=["Prescriptions & Prescription Items"])


@prescriptions_router.post("/prescriptions", status_code=status.HTTP_201_CREATED)
async def create_prescription(
    request_body: CreatePrescriptionRequest,
    raw_request: Request,
    current_user: DoctorUserDep,
    service: PrescriptionServiceDep,
) -> JSONResponse:
    """Create a DRAFT prescription atomically, including its line items
    (Doctor only). Patient is identified by phone (plaintext) rather than a
    path patient_id — find-or-create: an unregistered phone provisions a new
    patient account, whose one-time temp PIN is relayed in the response.

    Deviation from api-contract.md's original path-param form
    (POST /patients/{patient_id}/prescriptions) — replaced per updated
    product requirement.
    """
    ip_address = _get_client_ip(raw_request)
    result = await service.create_prescription(
        request=request_body, actor_payload=current_user, ip_address=ip_address
    )
    return success_response(
        data=result.model_dump(mode="json"),
        message="Prescription created successfully",
        code=status.HTTP_201_CREATED,
    )


@prescriptions_router.get("/patients/{patient_id}/prescriptions")
async def list_prescriptions(
    patient_id: uuid.UUID,
    current_user: AuthenticatedUserDep,
    service: PrescriptionServiceDep,
    status_filter: Optional[str] = Query(
        None, alias="status", pattern=r"^(DRAFT|APPROVED|CANCELLED)$"
    ),
    page: int = Query(1, ge=1, le=1000, description="Page number"),
    size: int = Query(10, ge=1, le=100, description="Items per page"),
) -> JSONResponse:
    """List a patient's prescriptions. Access is role-agnostic: self-owned,
    doctor-prescribed, or active-caregiver-linked — checked as independent
    facts, so one account can qualify through more than one."""
    result = await service.list_prescriptions(
        patient_id=patient_id,
        actor_payload=current_user,
        status=status_filter,
        page=page,
        size=size,
    )
    return success_response(
        data=result.model_dump(mode="json"),
        message="Prescription list fetched successfully",
    )


@prescriptions_router.get("/prescriptions/{prescription_id}")
async def get_prescription_detail(
    prescription_id: uuid.UUID,
    current_user: AuthenticatedUserDep,
    service: PrescriptionServiceDep,
) -> JSONResponse:
    """Fetch prescription detail. Access is role-agnostic, same derivation as
    list_prescriptions. Out-of-scope prescriptions return 404."""
    result = await service.get_prescription(
        prescription_id=prescription_id, actor_payload=current_user
    )
    return success_response(
        data=result.model_dump(mode="json"),
        message="Prescription details fetched successfully",
    )


@prescriptions_router.put("/prescriptions/{prescription_id}")
async def update_prescription(
    prescription_id: uuid.UUID,
    request_body: UpdatePrescriptionRequest,
    current_user: DoctorUserDep,
    service: PrescriptionServiceDep,
) -> JSONResponse:
    """Update a DRAFT prescription's diagnosis note (Doctor only, scoped to
    the doctor who created it)."""
    result = await service.update_prescription(
        prescription_id=prescription_id, request=request_body, actor_payload=current_user
    )
    return success_response(
        data=result.model_dump(mode="json"),
        message="Prescription updated successfully",
    )


@prescriptions_router.post("/prescriptions/{prescription_id}/approve")
async def approve_prescription(
    prescription_id: uuid.UUID,
    raw_request: Request,
    current_user: DoctorUserDep,
    service: PrescriptionServiceDep,
) -> JSONResponse:
    """Approve a DRAFT prescription, locking it (HITL gate; Doctor only,
    scoped to the doctor who created it)."""
    ip_address = _get_client_ip(raw_request)
    result = await service.approve_prescription(
        prescription_id=prescription_id, actor_payload=current_user, ip_address=ip_address
    )
    return success_response(
        data=result.model_dump(mode="json"),
        message="Prescription approved successfully",
    )


@prescriptions_router.post("/prescriptions/{prescription_id}/cancel")
async def cancel_prescription(
    prescription_id: uuid.UUID,
    request_body: CancelPrescriptionRequest,
    raw_request: Request,
    current_user: DoctorUserDep,
    service: PrescriptionServiceDep,
) -> JSONResponse:
    """Cancel a DRAFT or APPROVED prescription (Doctor only, scoped to the
    doctor who created it)."""
    ip_address = _get_client_ip(raw_request)
    result = await service.cancel_prescription(
        prescription_id=prescription_id,
        request=request_body,
        actor_payload=current_user,
        ip_address=ip_address,
    )
    return success_response(
        data=result.model_dump(mode="json"),
        message="Prescription cancelled successfully",
    )


@prescriptions_router.post(
    "/prescriptions/{prescription_id}/items", status_code=status.HTTP_201_CREATED
)
async def add_prescription_item(
    prescription_id: uuid.UUID,
    request_body: CreatePrescriptionItemRequest,
    raw_request: Request,
    current_user: DoctorUserDep,
    service: PrescriptionServiceDep,
) -> JSONResponse:
    """Add a medication line item to a DRAFT prescription (Doctor only,
    scoped to the doctor who created it). 422 if the prescription is no
    longer DRAFT."""
    ip_address = _get_client_ip(raw_request)
    result = await service.add_item(
        prescription_id=prescription_id,
        request=request_body,
        actor_payload=current_user,
        ip_address=ip_address,
    )
    return success_response(
        data=result.model_dump(mode="json"),
        message="Prescription item added successfully",
        code=status.HTTP_201_CREATED,
    )


@prescriptions_router.put("/prescriptions/{prescription_id}/items/{item_id}")
async def update_prescription_item(
    prescription_id: uuid.UUID,
    item_id: uuid.UUID,
    request_body: UpdatePrescriptionItemRequest,
    raw_request: Request,
    current_user: DoctorUserDep,
    service: PrescriptionServiceDep,
) -> JSONResponse:
    """Update a medication line item on a DRAFT prescription (Doctor only,
    scoped to the doctor who created it). 422 if the prescription is no
    longer DRAFT."""
    ip_address = _get_client_ip(raw_request)
    result = await service.update_item(
        prescription_id=prescription_id,
        item_id=item_id,
        request=request_body,
        actor_payload=current_user,
        ip_address=ip_address,
    )
    return success_response(
        data=result.model_dump(mode="json"),
        message="Prescription item updated successfully",
    )


@prescriptions_router.delete("/prescriptions/{prescription_id}/items/{item_id}")
async def delete_prescription_item(
    prescription_id: uuid.UUID,
    item_id: uuid.UUID,
    raw_request: Request,
    current_user: DoctorUserDep,
    service: PrescriptionServiceDep,
) -> JSONResponse:
    """Remove a medication line item from a DRAFT prescription (Doctor only,
    scoped to the doctor who created it). 422 if the prescription is no
    longer DRAFT. Hard delete."""
    ip_address = _get_client_ip(raw_request)
    await service.delete_item(
        prescription_id=prescription_id,
        item_id=item_id,
        actor_payload=current_user,
        ip_address=ip_address,
    )
    return success_response(
        data=MessageResponse(message="Prescription item removed successfully").model_dump(
            mode="json"
        ),
        message="Prescription item removed successfully",
    )
