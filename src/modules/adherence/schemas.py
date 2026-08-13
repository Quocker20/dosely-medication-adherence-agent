import uuid
from datetime import date, datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class RecordDoseActionRequest(BaseModel):
    """Request schema for POST /scheduled-doses/{scheduled_dose_id}/actions."""

    action: Literal["TAKEN", "SNOOZE", "SKIPPED"]
    action_source: str = "PATIENT_MOBILE_APP"
    payload: Dict[str, Any] = Field(default_factory=dict)


class AdherenceLogDetailResponse(BaseModel):
    """Response schema for a single adherence log entry."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    scheduled_dose_id: Optional[uuid.UUID] = None
    patient_id: uuid.UUID
    action: str
    performed_at: datetime
    action_source: str
    payload: Dict[str, Any]
    idempotency_key: Optional[str] = None


class AdherenceSummaryResponse(BaseModel):
    """Response schema for GET /patients/{patient_id}/adherence."""

    patient_id: uuid.UUID
    from_date: date
    to_date: date
    adherence_rate: float
    total_doses: int
    taken_doses: int
    skipped_doses: int
    missed_doses: int


class SymptomEntry(BaseModel):
    """A single symptom entry embedded in SubmitHealthSurveyRequest.symptoms."""

    symptom_code: str
    severity: Literal["MILD", "MODERATE", "SEVERE"]
    description: Optional[str] = None


class SubmitHealthSurveyRequest(BaseModel):
    """Request schema for POST /patients/{patient_id}/health-surveys."""

    survey_date: date
    answers_json: Dict[str, Any]
    symptoms: List[SymptomEntry] = Field(default_factory=list)


class HealthSurveyDetailResponse(BaseModel):
    """Response schema for POST /patients/{patient_id}/health-surveys."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    patient_id: uuid.UUID
    survey_date: date
    status: str
    submitted_at: Optional[datetime] = None


class TriggerSosRequest(BaseModel):
    """Request schema for POST /patients/{patient_id}/sos."""

    message: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ResolveAlertRequest(BaseModel):
    """Request schema for POST /alerts/{alert_id}/resolve."""

    resolution_note: str = Field(min_length=1)


class AlertDetailResponse(BaseModel):
    """Response schema for Alert records (SOS trigger, acknowledge, resolve, list)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    patient_id: uuid.UUID
    assigned_doctor_id: Optional[uuid.UUID] = None
    triggered_by_type: str
    alert_type: str
    severity: str
    status: str
    message: Optional[str] = None
    created_at: datetime
