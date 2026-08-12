import uuid
from datetime import date, datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class CreatePatientByDoctorRequest(BaseModel):
    """Request schema for Doctor creating a new Patient profile."""

    phone: str = Field(..., pattern=r"^\+?[0-9]{9,15}$")
    name: str = Field(..., max_length=255)
    dob: Optional[date] = None
    sex: Optional[str] = Field(None, pattern=r"^(MALE|FEMALE|OTHER)$")
    timezone: str = Field(default="Asia/Ho_Chi_Minh", max_length=50)
    emergency_note: Optional[str] = None


class PatientDetailResponse(BaseModel):
    """Response schema representing full Patient profile.

    Used by: GET /doctors/patients, GET /doctors/patients/{id}.
    Also embedded inside CreatePatientResponse for the create endpoint.
    """

    model_config = ConfigDict(from_attributes=True)

    user_id: uuid.UUID
    phone: str
    role: str = "PATIENT"
    status: str
    name: str
    dob: Optional[date] = None
    sex: Optional[str] = None
    timezone: str
    privacy_consent_status: Optional[str] = None
    emergency_note: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class CreatePatientResponse(BaseModel):
    """Response schema for POST /doctors/patients.

    Wraps PatientDetailResponse with a one-time temp_password field, mirroring
    CreateDoctorResponse — schema.md/api-contract.md list the bare
    PatientDetailResponse here, but a patient authenticates via phone+PIN same
    as a doctor, so a temp PIN must be relayed at creation time or the patient
    account is unusable. Deviation is intentional; flagged to the team.
    """

    patient: PatientDetailResponse
    temp_password: str
