import json
import uuid
from datetime import date, datetime, time
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class RecordDoseActionRequest(BaseModel):
    """Request schema for POST /scheduled-doses/{scheduled_dose_id}/actions."""

    action: Literal["TAKEN", "SNOOZE", "SKIPPED"]
    action_source: str = "PATIENT_MOBILE_APP"
    payload: dict[str, Any] = Field(default_factory=dict)


class BatchRecordDoseActionRequest(BaseModel):
    """Request schema for POST /scheduled-doses/batch-actions."""

    dose_ids: list[uuid.UUID] = Field(..., min_length=1)
    action: Literal["TAKEN", "SNOOZE", "SKIPPED"]
    action_source: str = "PATIENT_MOBILE_APP"
    payload: dict[str, Any] = Field(default_factory=dict)


class BatchRecordDoseActionResponse(BaseModel):
    """Response schema for batch dose action execution."""

    patient_id: uuid.UUID
    action: str
    updated_dose_count: int
    updated_dose_ids: list[uuid.UUID]
    logs: list["AdherenceLogDetailResponse"]



class AdherenceLogDetailResponse(BaseModel):
    """Response schema for a single adherence log entry."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    scheduled_dose_id: uuid.UUID | None = None
    patient_id: uuid.UUID
    action: str
    performed_at: datetime
    action_source: str
    payload: dict[str, Any]
    idempotency_key: str | None = None


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
    description: str | None = None


class RoutineDeviationEntry(BaseModel):
    """A single routine-deviation entry embedded in
    SubmitHealthSurveyRequest.routine_deviations. Deliberately a structured
    field, not folded into answers_json — answers_json is excluded from all
    downstream aggregation (see adherence_review/repository.py), so anything
    that needs to be acted on must not live there."""

    anchor: Literal["breakfast", "lunch", "dinner", "sleep"]
    overridden_time: time
    reason: str | None = None


class SubmitHealthSurveyRequest(BaseModel):
    """Request schema for POST /patients/{patient_id}/health-surveys."""

    survey_date: date
    answers_json: dict[str, Any]
    symptoms: list[SymptomEntry] = Field(default_factory=list)
    routine_deviations: list[RoutineDeviationEntry] = Field(default_factory=list)


class HealthSurveyDetailResponse(BaseModel):
    """Response schema for POST /patients/{patient_id}/health-surveys."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    patient_id: uuid.UUID
    survey_date: date
    status: str
    submitted_at: datetime | None = None


class SymptomReportDetailResponse(BaseModel):
    """Response schema for a single symptom entry, embedded in
    HealthSurveyFullDetailResponse.symptoms (GET .../health-surveys/{id})."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    survey_id: uuid.UUID | None = None
    symptom_code: str
    severity: str
    description: str | None = None
    reported_at: datetime
    source: str


class HealthSurveyListItemResponse(BaseModel):
    """Response schema for one row of GET /health-surveys and
    GET /patients/{patient_id}/health-surveys — summary only, no answers_json
    or symptom list (see HealthSurveyFullDetailResponse for that)."""

    id: uuid.UUID
    patient_id: uuid.UUID
    patient_name: str
    survey_date: date
    status: str
    submitted_at: datetime | None = None
    symptom_count: int
    max_severity: str | None = None


class HealthSurveyFullDetailResponse(BaseModel):
    """Response schema for GET /health-surveys/{survey_id}."""

    id: uuid.UUID
    patient_id: uuid.UUID
    patient_name: str
    survey_date: date
    status: str
    submitted_at: datetime | None = None
    answers_json: dict[str, Any]
    symptoms: list[SymptomReportDetailResponse]


SOS_MESSAGE_MAX_CHARS = 500
SOS_METADATA_MAX_BYTES = 4096


class TriggerSosRequest(BaseModel):
    """Request schema for POST /patients/{patient_id}/sos.

    triggered_by_type/severity default to the SOS-button case, so an existing
    client that sends neither keeps its current behaviour. They exist because
    the agent raises alerts through this same endpoint after detecting a severe
    symptom in chat: without them every such alert is filed as a button press,
    and the doctor's dashboard cannot tell a tap from a detection. Values match
    ck_alerts_triggered_by_type / ck_alerts_severity — no migration needed.
    """

    message: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    triggered_by_type: Literal["SOS_BUTTON", "SEVERE_SYMPTOM", "MISSED_DOSES"] = "SOS_BUTTON"
    severity: Literal["CRITICAL", "HIGH", "MEDIUM"] = "CRITICAL"

    @field_validator("message")
    @classmethod
    def _bound_message(cls, value: str | None) -> str | None:
        """SEC-09: cap at SOS_MESSAGE_MAX_CHARS by truncating, never rejecting.

        The agent builds `message` from reason + the patient's own words, so it
        can legitimately run long; a 422 here would drop a genuine safety
        alert. Truncation bounds storage without ever blocking one.
        """
        if value is not None and len(value) > SOS_MESSAGE_MAX_CHARS:
            return value[: SOS_MESSAGE_MAX_CHARS - 1] + "…"
        return value

    @field_validator("metadata")
    @classmethod
    def _bound_metadata(cls, value: dict[str, Any]) -> dict[str, Any]:
        """SEC-09: serialized metadata must fit SOS_METADATA_MAX_BYTES. The
        agent sends ~40 bytes ({"source": "agent_auto_detect"}); its evidence
        text travels in `message`, so this cap leaves ample headroom."""
        size = len(json.dumps(value, ensure_ascii=False, default=str).encode("utf-8"))
        if size > SOS_METADATA_MAX_BYTES:
            raise ValueError(
                f"metadata must be at most {SOS_METADATA_MAX_BYTES} bytes when serialized"
            )
        return value


class ResolveAlertRequest(BaseModel):
    """Request schema for POST /alerts/{alert_id}/resolve."""

    resolution_note: str = Field(min_length=1, max_length=1000)


class AlertDetailResponse(BaseModel):
    """Response schema for Alert records (SOS trigger, acknowledge, resolve, list)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    patient_id: uuid.UUID
    # Not on the Alert ORM model (no relationship — see structure.md's
    # "no implicit lazy loading" convention); the service attaches this
    # after model_validate via PatientRepository, batched for list_alerts so
    # a page of N alerts costs one extra query, not N.
    patient_name: str | None = None
    assigned_doctor_id: uuid.UUID | None = None
    triggered_by_type: str
    alert_type: str
    severity: str
    status: str
    message: str | None = None
    created_at: datetime
