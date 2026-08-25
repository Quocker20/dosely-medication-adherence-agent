import uuid
from datetime import date, datetime, time
from typing import List, Optional
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


class UpdateRoutineRequest(BaseModel):
    """Request schema for setting/updating patient daily routine timestamps."""

    wake_time: Optional[time] = None
    breakfast_time: Optional[time] = None
    lunch_time: Optional[time] = None
    dinner_time: Optional[time] = None
    sleep_time: Optional[time] = None


class PatientRoutineResponse(BaseModel):
    """Response schema representing the patient's current daily routine.

    Used by: GET/PUT /patients/{patient_id}/routine.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    patient_id: uuid.UUID
    wake_time: Optional[time] = None
    breakfast_time: Optional[time] = None
    lunch_time: Optional[time] = None
    dinner_time: Optional[time] = None
    sleep_time: Optional[time] = None
    updated_at: datetime


class PatientOnboardingRequest(BaseModel):
    """Request schema for PATIENT self-onboarding on first login.

    Payload for POST /patients/me/profile.
    """

    name: str = Field(..., max_length=255)
    dob: Optional[date] = None
    sex: Optional[str] = Field(None, pattern=r"^(MALE|FEMALE|OTHER)$")
    timezone: str = Field(default="Asia/Ho_Chi_Minh", max_length=50)
    emergency_note: Optional[str] = None
    routine: UpdateRoutineRequest


class PatientProfileDetailResponse(BaseModel):
    """Response schema combining profile and routine after onboarding.

    Used by: POST /patients/me/profile.
    """

    profile: PatientDetailResponse
    routine: PatientRoutineResponse


class CreateCaregiverLinkRequest(BaseModel):
    """Request schema for linking a Caregiver account to a patient."""

    caregiver_phone: str = Field(..., pattern=r"^\+?[0-9]{9,15}$")
    relationship: Optional[str] = Field(None, max_length=50)
    channels: List[str] = Field(default_factory=lambda: ["APP_NOTIFICATION"])


class CaregiverLinkDetailResponse(BaseModel):
    """Response schema representing a Caregiver-Patient association link.

    schema.md lists no temp_password field here, but caregiver_user_id is a
    NOT NULL FK — a phone with no existing account must get one provisioned
    on the spot (find-or-create), same as CreatePatientResponse. temp_password
    is populated only when this call just created that account; an existing
    caregiver being re-linked leaves it null. Deviation is intentional.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    patient_id: uuid.UUID
    caregiver_user_id: uuid.UUID
    relationship: Optional[str] = None
    channels: List[str]
    status: str
    created_at: datetime
    temp_password: Optional[str] = None
