import uuid
from datetime import date, datetime, time

from pydantic import BaseModel, ConfigDict, Field


class CreatePatientByDoctorRequest(BaseModel):
    """Request schema for Doctor creating a new Patient profile."""

    phone: str = Field(..., pattern=r"^\+?[0-9]{9,15}$")
    name: str = Field(..., max_length=255)
    dob: date | None = None
    sex: str | None = Field(None, pattern=r"^(MALE|FEMALE|OTHER)$")
    timezone: str = Field(default="Asia/Ho_Chi_Minh", max_length=50)
    emergency_note: str | None = None


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
    dob: date | None = None
    sex: str | None = None
    timezone: str
    privacy_consent_status: str | None = None
    emergency_note: str | None = None
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

    wake_time: time | None = None
    breakfast_time: time | None = None
    lunch_time: time | None = None
    dinner_time: time | None = None
    sleep_time: time | None = None


class PatientRoutineResponse(BaseModel):
    """Response schema representing the patient's current daily routine.

    Used by: GET/PUT /patients/{patient_id}/routine.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    patient_id: uuid.UUID
    wake_time: time | None = None
    breakfast_time: time | None = None
    lunch_time: time | None = None
    dinner_time: time | None = None
    sleep_time: time | None = None
    updated_at: datetime


class PatientOnboardingRequest(BaseModel):
    """Request schema for PATIENT self-onboarding on first login.

    Payload for POST /patients/me/profile.
    """

    name: str = Field(..., max_length=255)
    dob: date | None = None
    sex: str | None = Field(None, pattern=r"^(MALE|FEMALE|OTHER)$")
    timezone: str = Field(default="Asia/Ho_Chi_Minh", max_length=50)
    emergency_note: str | None = None
    routine: UpdateRoutineRequest


class PatientProfileDetailResponse(BaseModel):
    """Response schema combining profile and routine after onboarding.

    Used by: POST /patients/me/profile.
    """

    profile: PatientDetailResponse
    routine: PatientRoutineResponse
