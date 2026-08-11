from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=5000, description="Tin nhắn từ user")
    # TODO: nên lấy từ auth token của request thay vì để client tự khai —
    # xem cong_viec.md §4.5. Để required ở đây để tool không âm thầm chạy
    # thiếu patient_id, nhưng đây chưa phải cơ chế xác thực thật.
    patient_id: str = Field(..., min_length=1, description="Mã UUID của bệnh nhân")


class ChatResponse(BaseModel):
    response: str = Field(..., description="Phản hồi từ agent")
