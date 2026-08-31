import uuid
from datetime import date, datetime
from typing import Any, Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field


class GenerateScheduleRequest(BaseModel):
    """Request schema for POST /patients/{patient_id}/schedules/generate."""

    reason: str | None = None


class RescheduleRequest(BaseModel):
    """Request schema for POST /patients/{patient_id}/schedules/reschedule."""

    reason: str | None = None


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
    prescription_id: uuid.UUID | None = None
    trigger_type: str
    graph_version: str
    status: str
    latency_ms: int | None = None
    error_code: str | None = None
    # Lý do dừng ở dạng đọc được (error_code chỉ là tên class exception) — portal
    # dựa vào đây để bác sĩ biết phải sửa thuốc nào khi status=NEEDS_REVIEW.
    error_message: str | None = None
    generated_dose_count: int | None = None
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
    timezone: str | None = None
    doses: list[dict[str, Any]] = Field(default_factory=list)


class NextDoseResponse(BaseModel):
    """Deterministic next-dose result for the authenticated patient."""

    status: Literal["UPCOMING", "NO_SCHEDULE", "NO_UPCOMING"]
    local_date: date
    timezone: str | None = None
    dose: dict[str, Any] | None = None


class ChatRequest(BaseModel):
    """Request schema for POST /chat (text chat with the patient AI agent).

    No patient_id field: the agent always acts on the authenticated caller's
    own record, taken from the access token's `sub`. Accepting it from the
    body would let any caller converse — and write dose actions / raise
    alerts — as an arbitrary patient.
    """

    model_config = ConfigDict(populate_by_name=True)

    message: str = Field(..., min_length=1, max_length=5000, description="Tin nhắn từ bệnh nhân")
    conversation_id: uuid.UUID | None = Field(
        None,
        validation_alias=AliasChoices("conversationId", "conversation_id"),
        serialization_alias="conversationId",
    )
    client_date: date | None = Field(
        None,
        validation_alias=AliasChoices("clientDate", "client_date"),
        serialization_alias="clientDate",
    )
    client_datetime: datetime | None = Field(
        None,
        validation_alias=AliasChoices("clientDateTime", "client_datetime"),
        serialization_alias="clientDateTime",
    )


class ChatResponse(BaseModel):
    """Response schema for POST /chat."""

    model_config = ConfigDict(populate_by_name=True)

    response: str = Field(..., description="Phản hồi từ agent")
    conversation_id: uuid.UUID | None = Field(None, alias="conversationId")


class VoiceChatResponse(BaseModel):
    """Response schema for POST /chat/voice."""

    model_config = ConfigDict(populate_by_name=True)

    transcript: str = Field(..., description="Văn bản nhận dạng được từ giọng nói của bệnh nhân")
    response: str = Field(..., description="Phản hồi từ agent (dạng chữ)")
    conversation_id: uuid.UUID | None = Field(None, alias="conversationId")
    audio_base64: str | None = Field(
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
