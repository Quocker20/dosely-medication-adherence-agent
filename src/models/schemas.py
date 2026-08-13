from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=5000, description="Tin nhắn từ user")
    # TODO: nên lấy từ auth token của request thay vì để client tự khai —
    # xem cong_viec.md §4.5. Để required ở đây để tool không âm thầm chạy
    # thiếu patient_id, nhưng đây chưa phải cơ chế xác thực thật.
    patient_id: str = Field(..., min_length=1, description="Mã UUID của bệnh nhân")


class ChatResponse(BaseModel):
    response: str = Field(..., description="Phản hồi từ agent")


class VoiceChatResponse(BaseModel):
    transcript: str = Field(..., description="Văn bản nhận dạng được từ giọng nói bệnh nhân")
    response: str = Field(..., description="Phản hồi từ agent (dạng chữ)")
    # None khi TTS lỗi — vẫn trả transcript+response dạng chữ, không chặn
    # cả phản hồi chỉ vì thiếu audio (fail-open, xem src/services/speech.py).
    audio_base64: str | None = Field(
        default=None, description="Audio mp3 của response, base64. None nếu TTS lỗi."
    )
