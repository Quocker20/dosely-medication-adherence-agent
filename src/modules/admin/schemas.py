from ipaddress import IPv4Address, IPv6Address
import uuid
from datetime import datetime
from typing import Any, Dict, Optional, Union
from pydantic import BaseModel, ConfigDict, Field


class CreateDoctorRequest(BaseModel):
    """Request schema for Admin creating a new Doctor."""

    phone: str = Field(..., pattern=r"^\+?[0-9]{9,15}$")
    name: str = Field(..., max_length=255)
    license_no: str = Field(..., max_length=100)
    specialty: Optional[str] = Field(None, max_length=150)


class UpdateDoctorRequest(BaseModel):
    """Request schema for Admin updating Doctor details."""

    name: Optional[str] = Field(None, max_length=255)
    specialty: Optional[str] = Field(None, max_length=150)
    status: Optional[str] = Field(None, pattern=r"^(ACTIVE|INACTIVE)$")


class DoctorDetailResponse(BaseModel):
    """Response schema representing full Doctor profile.

    Used by: GET /admin/doctors, GET /admin/doctors/{id}, PUT /admin/doctors/{id}.
    Also embedded inside CreateDoctorResponse for the create endpoint.
    """

    model_config = ConfigDict(from_attributes=True)

    user_id: uuid.UUID
    phone: str
    role: str = "DOCTOR"
    status: str
    name: str
    license_no: str
    specialty: Optional[str] = None
    created_at: datetime


class CreateDoctorResponse(BaseModel):
    """Response schema for POST /admin/doctors.

    Wraps DoctorDetailResponse with a one-time temp_password field.
    Admin must relay this to the doctor; it is shown only once.
    Doctor is forced to change it on first login (must_change_password=True,
    derived from users.password_changed_at IS NULL).
    """

    doctor: DoctorDetailResponse
    temp_password: str


class AuditLogListResponse(BaseModel):
    """Response schema for system audit logs."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    actor_user_id: Optional[uuid.UUID] = None
    action: str
    entity_type: str
    entity_id: Optional[uuid.UUID] = None
    old_values: Optional[Dict[str, Any]] = None
    new_values: Optional[Dict[str, Any]] = None
    ip_address: Optional[Union[str, IPv4Address, IPv6Address]] = None
    created_at: datetime

