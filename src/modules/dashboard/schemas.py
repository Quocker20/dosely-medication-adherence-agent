import uuid
from datetime import date, datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from src.modules.adherence.schemas import AlertDetailResponse


class DashboardPatientListResponse(BaseModel):
    """Response schema for one row of GET /dashboard/patients."""

    patient_id: uuid.UUID
    patient_name: str
    adherence_rate: float
    open_alerts_count: int
    last_survey_date: Optional[date] = None


class DashboardAdherenceSummary(BaseModel):
    """Adherence block embedded in DashboardPatientDetailResponse.

    Deliberately narrower than AdherenceSummaryResponse: the dashboard shows a
    headline rate over a rolling window, not a caller-chosen [from, to] range,
    so it carries no date fields to be misread as one.
    """

    adherence_rate: float
    total_doses: int
    taken_doses: int
    skipped_doses: int
    missed_doses: int
    window_days: int


class DashboardPatientSummary(BaseModel):
    """Identity block embedded in DashboardPatientDetailResponse."""

    user_id: uuid.UUID
    name: str
    phone: str


class DashboardPatientDetailResponse(BaseModel):
    """Response schema for GET /dashboard/patients/{patient_id}."""

    patient: DashboardPatientSummary
    active_prescriptions_count: int
    adherence_summary: DashboardAdherenceSummary
    recent_alerts: List[AlertDetailResponse] = Field(default_factory=list)


class WebSocketEventStream(BaseModel):
    """One JSON frame pushed to a connected dashboard client over WS /ws/dashboard."""

    event_type: str
    timestamp: datetime
    data: Dict[str, Any] = Field(default_factory=dict)


class RoutineUpdatedEventData(BaseModel):
    """Minimal marker sent after a committed patient routine change."""

    patient_id: uuid.UUID
    updated_at: datetime


class RoutineUpdatedEventEnvelope(BaseModel):
    """Typed websocket frame for ``routine.updated`` (no routine times)."""

    event_type: Literal["routine.updated"]
    timestamp: datetime
    data: RoutineUpdatedEventData


class ScheduleUpdatedEventData(BaseModel):
    """Minimal marker sent after a generated schedule has been persisted."""

    patient_id: uuid.UUID
    updated_at: datetime


class ScheduleUpdatedEventEnvelope(BaseModel):
    """Typed websocket frame for ``schedule.updated`` (no medication data)."""

    event_type: Literal["schedule.updated"]
    timestamp: datetime
    data: ScheduleUpdatedEventData
