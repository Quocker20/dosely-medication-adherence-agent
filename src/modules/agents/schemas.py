import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional

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


class ActiveDoseResponse(BaseModel):
    """A concrete scheduled dose with its generation-time prescription data.

    Snapshot fields are optional so pre-0011 rows remain readable. A null
    dose_value must be presented as unknown, never reconstructed by choosing
    one of the parent prescription item's four dose columns.
    """

    scheduled_dose_id: uuid.UUID
    prescription_item_id: uuid.UUID
    medication_id: Optional[uuid.UUID] = None
    medication_name: str
    current_scheduled_at: datetime
    dose_slot: Optional[str] = None
    dose_value: Optional[Decimal] = None
    dose_unit: Optional[str] = None
    meal_relation: Optional[str] = None
    status: str
    snooze_count: int


class ActiveScheduleResponse(BaseModel):
    """Response schema for GET /patients/{patient_id}/schedules?date=.

    Each row carries stable item/catalog identifiers and the exact
    slot-specific prescription snapshot selected during generation.
    """

    patient_id: uuid.UUID
    date: date
    doses: List[ActiveDoseResponse] = Field(default_factory=list)
