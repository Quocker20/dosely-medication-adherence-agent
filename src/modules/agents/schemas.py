import uuid
from datetime import date, datetime, time
from typing import Any, Dict, List, Literal, Optional

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, model_validator

# How far ahead the chat agent may book a routine override. Kept small on
# purpose: the agent only resolves plain relative wording ("hôm nay", "mai",
# "ngày kia"), and anything a patient expresses less directly is asked back
# rather than guessed — a misparsed date moves the wrong day's doses. UI
# clients are not bound by this; they send an absolute override_date and are
# limited only by the schedule horizon.
MAX_DEVIATION_DAY_OFFSET = 2


class GenerateScheduleRequest(BaseModel):
    """Request schema for POST /patients/{patient_id}/schedules/generate."""

    reason: Optional[str] = None


class RescheduleRequest(BaseModel):
    """Request schema for POST /patients/{patient_id}/schedules/reschedule."""

    reason: Optional[str] = None


RoutineAnchor = Literal["breakfast", "lunch", "dinner", "sleep"]
DeviationSource = Literal["SURVEY", "CHAT"]


class ReportRoutineDeviationRequest(BaseModel):
    """Request schema for POST /patients/{patient_id}/routine-overrides.

    The target day is given EITHER as an absolute `override_date` (what a UI
    client with a date picker sends) OR as a `day_offset` in days from today
    (what the chat agent sends). Exactly one must be present.

    The offset form exists because the agent has no reliable way to know the
    patient's local date: it previously fell back to the *server's* date,
    which could differ by a day from the patient's timezone and silently move
    the wrong day's doses. Resolving the offset server-side, against the
    patient's own timezone, removes that whole class of bug rather than
    patching it. Either way the service re-derives and re-validates the date,
    so a stale client value fails closed (422) instead of applying to the
    wrong day.
    """

    override_date: date | None = None
    day_offset: int | None = Field(default=None, ge=0, le=MAX_DEVIATION_DAY_OFFSET)
    anchor: RoutineAnchor
    overridden_time: time
    source: DeviationSource
    reason: str | None = None

    @model_validator(mode="after")
    def exactly_one_day_reference(self) -> "ReportRoutineDeviationRequest":
        if (self.override_date is None) == (self.day_offset is None):
            raise ValueError("Provide exactly one of override_date or day_offset")
        return self


class CancelRoutineOverrideRequest(BaseModel):
    """Request schema for DELETE /patients/{patient_id}/routine-overrides.

    Booking an override ahead of time means the patient must also be able to
    take it back ("thôi ngày kia không bận nữa"); without this the row sits
    there until its day passes and the schedule stays shifted.
    """

    override_date: date
    anchor: RoutineAnchor


class RecentRoutineOverrideResponse(BaseModel):
    """One row of GET .../routine-overrides/recent — read-only history used
    to phrase a smarter clarifying question, never to auto-apply a time."""

    override_date: date
    overridden_time: time


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
    # Lý do dừng ở dạng đọc được (error_code chỉ là tên class exception) — portal
    # dựa vào đây để bác sĩ biết phải sửa thuốc nào khi status=NEEDS_REVIEW.
    error_message: Optional[str] = None
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
    timezone: Optional[str] = None
    doses: List[Dict[str, Any]] = Field(default_factory=list)


class NextDoseResponse(BaseModel):
    """Deterministic next-dose result for the authenticated patient."""

    status: Literal["UPCOMING", "NO_SCHEDULE", "NO_UPCOMING"]
    local_date: date
    timezone: Optional[str] = None
    dose: Optional[Dict[str, Any]] = None


class ChatRequest(BaseModel):
    """Request schema for POST /chat (text chat with the patient AI agent).

    No patient_id field: the agent always acts on the authenticated caller's
    own record, taken from the access token's `sub`. Accepting it from the
    body would let any caller converse — and write dose actions / raise
    alerts — as an arbitrary patient.
    """

    model_config = ConfigDict(populate_by_name=True)

    message: str = Field(..., min_length=1, max_length=5000, description="Tin nhắn từ bệnh nhân")
    conversation_id: Optional[uuid.UUID] = Field(
        None,
        validation_alias=AliasChoices("conversationId", "conversation_id"),
        serialization_alias="conversationId",
    )
    client_date: Optional[date] = Field(
        None,
        validation_alias=AliasChoices("clientDate", "client_date"),
        serialization_alias="clientDate",
    )
    client_datetime: Optional[datetime] = Field(
        None,
        validation_alias=AliasChoices("clientDateTime", "client_datetime"),
        serialization_alias="clientDateTime",
    )


class ChatResponse(BaseModel):
    """Response schema for POST /chat."""

    model_config = ConfigDict(populate_by_name=True)

    response: str = Field(..., description="Phản hồi từ agent")
    conversation_id: Optional[uuid.UUID] = Field(None, alias="conversationId")


class VoiceChatResponse(BaseModel):
    """Response schema for POST /chat/voice."""

    model_config = ConfigDict(populate_by_name=True)

    transcript: str = Field(..., description="Văn bản nhận dạng được từ giọng nói của bệnh nhân")
    response: str = Field(..., description="Phản hồi từ agent (dạng chữ)")
    conversation_id: Optional[uuid.UUID] = Field(None, alias="conversationId")
    audio_base64: Optional[str] = Field(
        None, description="Phản hồi dạng giọng nói (mp3, base64) — null nếu TTS lỗi (fail-open)"
    )


class ChatConversationListItem(BaseModel):
    """Item schema for GET /chat/conversations list."""

    id: uuid.UUID
    title: str
    preview: str | None = None
    message_count: int = Field(default=0, alias="messageCount")
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")

    model_config = ConfigDict(populate_by_name=True, from_attributes=True)


class ChatMessageItem(BaseModel):
    """Item schema for message in conversation detail."""

    id: uuid.UUID
    role: str
    content: str
    intent: str | None = None
    created_at: datetime = Field(alias="createdAt")

    model_config = ConfigDict(populate_by_name=True, from_attributes=True)


class ChatConversationDetailResponse(BaseModel):
    """Response schema for GET /chat/conversations/{conversation_id}."""

    id: uuid.UUID
    title: str
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")
    messages: list[ChatMessageItem] = Field(default_factory=list)
    has_more: bool = Field(default=False, alias="hasMore")
    next_cursor: str | None = Field(default=None, alias="nextCursor")

    model_config = ConfigDict(populate_by_name=True, from_attributes=True)
