import uuid
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class GenerateScheduleRequest(BaseModel):
    """Request schema for POST /patients/{patient_id}/schedules/generate."""

    reason: Optional[str] = None


class RescheduleRequest(BaseModel):
    """Request schema for POST /patients/{patient_id}/schedules/reschedule."""

    reason: Optional[str] = None


class AgentRunAsyncResponse(BaseModel):
    """202 Accepted response wrapping the dispatched agent run's id."""

    agent_run_id: uuid.UUID
    status: str
    message: str


class AgentRunStatusResponse(BaseModel):
    """Response schema for GET /agent-runs/{agent_run_id}."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    agent_type: str
    patient_id: uuid.UUID
    prescription_id: Optional[uuid.UUID] = None
    trigger_type: str
    graph_version: str
    status: str
    latency_ms: Optional[int] = None
    error_code: Optional[str] = None
    generated_dose_count: Optional[int] = None
    created_at: datetime


class ActiveScheduleResponse(BaseModel):
    """Response schema for GET /patients/{patient_id}/schedules?date=.

    doses stays List[Dict[str, Any]] per schema.md §6.4 rather than a typed
    row model — each dict carries scheduled_dose_id, medication_name (joined
    from PrescriptionItem.display_name), current_scheduled_at, status,
    snooze_count.
    """

    patient_id: uuid.UUID
    date: date
    doses: List[Dict[str, Any]] = Field(default_factory=list)
