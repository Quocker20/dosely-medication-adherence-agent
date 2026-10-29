import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, model_validator


class CreateCaregiverLinkRequest(BaseModel):
    phone: str = Field(..., min_length=1, max_length=20, description="Phone number of caregiver")
    relationship: str | None = Field(
        None, max_length=50, description="Relationship to patient (e.g. child, spouse)"
    )

    @model_validator(mode="before")
    @classmethod
    def handle_phone_alias(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "caregiver_phone" in data and "phone" not in data:
                data["phone"] = data["caregiver_phone"]
        return data


class CaregiverLinkDetailResponse(BaseModel):
    id: uuid.UUID
    patient_id: uuid.UUID
    phone: str
    relationship: str | None = None
    link_code: str | None = None
    telegram_deep_link: str | None = None
    status: str
    telegram_bound_at: datetime | None = None
    last_message_sent_at: datetime | None = None
    created_at: datetime
