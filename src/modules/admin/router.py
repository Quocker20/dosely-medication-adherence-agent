import uuid
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_db, require_roles
from src.core.response import success_response
from src.modules.admin.repository import AuditLogRepository, DoctorRepository
from src.modules.admin.schemas import (
    CreateDoctorRequest,
    UpdateDoctorRequest,
)
from src.modules.admin.service import AdminService
from src.modules.auth.repository import AuthRepository


def _get_client_ip(request: Request) -> str:
    """Extract client IP address from request headers or host."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "127.0.0.1"


def get_admin_service(db: Annotated[AsyncSession, Depends(get_db)]) -> AdminService:
    """Dependency factory providing AdminService instance."""
    doctor_repo = DoctorRepository(db)
    audit_repo = AuditLogRepository(db)
    auth_repo = AuthRepository(db)
    return AdminService(
        db=db,
        doctor_repository=doctor_repo,
        audit_repository=audit_repo,
        auth_repository=auth_repo,
    )


AdminServiceDep = Annotated[AdminService, Depends(get_admin_service)]
AdminUserDep = Annotated[dict, Depends(require_roles("ADMIN"))]

router = APIRouter(prefix="/admin", tags=["Admin & Doctor Management"])


@router.post("/doctors", status_code=status.HTTP_201_CREATED)
async def create_doctor(
    request_body: CreateDoctorRequest,
    raw_request: Request,
    current_user: AdminUserDep,
    service: AdminServiceDep,
) -> JSONResponse:
    """Create a new Doctor account and profile (Admin only)."""
    ip_address = _get_client_ip(raw_request)
    result = await service.create_doctor(
        request=request_body,
        actor_payload=current_user,
        ip_address=ip_address,
    )
    return success_response(
        data=result.model_dump(mode="json"),
        message="Doctor account created successfully",
        code=status.HTTP_201_CREATED,
    )


@router.get("/doctors")
async def list_doctors(
    current_user: AdminUserDep,
    service: AdminServiceDep,
    page: int = Query(1, ge=1, description="Page number"),
    size: int = Query(10, ge=1, le=100, description="Items per page"),
    search: Optional[str] = Query(None, description="Search by name, phone, or license_no"),
) -> JSONResponse:
    """Query paginated doctor roster (Admin only)."""
    result = await service.list_doctors(page=page, size=size, search=search)
    return success_response(
        data=result.model_dump(mode="json"),
        message="Doctor list fetched successfully",
    )


@router.get("/doctors/{doctor_id}")
async def get_doctor_detail(
    doctor_id: uuid.UUID,
    current_user: AdminUserDep,
    service: AdminServiceDep,
) -> JSONResponse:
    """Fetch specific doctor profile by user ID (Admin only)."""
    result = await service.get_doctor(doctor_id=doctor_id)
    return success_response(
        data=result.model_dump(mode="json"),
        message="Doctor details fetched successfully",
    )


@router.put("/doctors/{doctor_id}")
async def update_doctor(
    doctor_id: uuid.UUID,
    request_body: UpdateDoctorRequest,
    raw_request: Request,
    current_user: AdminUserDep,
    service: AdminServiceDep,
) -> JSONResponse:
    """Update doctor profile details or account status (Admin only)."""
    ip_address = _get_client_ip(raw_request)
    result = await service.update_doctor(
        doctor_id=doctor_id,
        request=request_body,
        actor_payload=current_user,
        ip_address=ip_address,
    )
    return success_response(
        data=result.model_dump(mode="json"),
        message="Doctor profile updated successfully",
    )


@router.delete("/doctors/{doctor_id}")
async def deactivate_doctor(
    doctor_id: uuid.UUID,
    raw_request: Request,
    current_user: AdminUserDep,
    service: AdminServiceDep,
) -> JSONResponse:
    """Deactivate doctor account (Admin only)."""
    ip_address = _get_client_ip(raw_request)
    result = await service.deactivate_doctor(
        doctor_id=doctor_id,
        actor_payload=current_user,
        ip_address=ip_address,
    )
    return success_response(
        data=None,
        message=result.message,
    )


@router.get("/audit-logs")
async def list_audit_logs(
    current_user: AdminUserDep,
    service: AdminServiceDep,
    page: int = Query(1, ge=1, description="Page number"),
    size: int = Query(10, ge=1, le=100, description="Items per page"),
    actor_id: Optional[uuid.UUID] = Query(None, alias="actorId", description="Filter by actor user ID"),
    entity_type: Optional[str] = Query(None, alias="entityType", description="Filter by entity type"),
) -> JSONResponse:
    """Query paginated system audit logs (Admin only)."""
    result = await service.list_audit_logs(
        page=page,
        size=size,
        actor_id=actor_id,
        entity_type=entity_type,
    )
    return success_response(
        data=result.model_dump(mode="json"),
        message="Audit logs fetched successfully",
    )
