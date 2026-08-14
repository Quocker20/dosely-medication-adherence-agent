from typing import Optional

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """Request schema cho POST /chat (chat AI bằng chữ)."""

    message: str = Field(..., min_length=1, max_length=5000, description="Tin nhắn từ bệnh nhân")


class ChatResponse(BaseModel):
    """Response schema cho POST /chat."""

    response: str = Field(..., description="Phản hồi từ agent")


class VoiceChatResponse(BaseModel):
    """Response schema cho POST /chat/voice."""

    transcript: str = Field(..., description="Văn bản nhận dạng được từ giọng nói của bệnh nhân")
    response: str = Field(..., description="Phản hồi từ agent (dạng chữ)")
    audio_base64: Optional[str] = Field(
        None, description="Phản hồi dạng giọng nói (mp3, base64) — null nếu TTS lỗi (fail-open)"
    )
