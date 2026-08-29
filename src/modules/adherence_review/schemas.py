import uuid
from datetime import date, datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict


class AdherenceReviewDetailResponse(BaseModel):
    """One nightly graded-adherence review row.

    Exposed to the same PATIENT/DOCTOR/CAREGIVER audience as
    HealthSurveyFullDetailResponse, with no role-based trimming -- llm_reasoning
    is doctor-facing content but this endpoint does not hide it from the
    patient it is about, matching that existing precedent rather than
    inventing a new one. Internal-only linkage (alert_id,
    notification_delivery_id, model_version, prompt_version) is not exposed;
    those are audit fields, not part of the patient/doctor-facing contract.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    patient_id: uuid.UUID
    review_date: date
    window_start: date
    window_end: date
    severity: str
    days_in_severity: int
    remedy_class: Optional[str] = None
    action_taken: str
    # Frozen severity-side numbers this review's severity was computed from
    # (see AdherenceIndicatorRepository / AdherenceReviewService) -- contains
    # no PII, same population of fields as SeverityIndicators.
    indicators: Dict[str, Any]
    llm_reasoning: Optional[str] = None
    llm_confidence: Optional[str] = None
    created_at: datetime
