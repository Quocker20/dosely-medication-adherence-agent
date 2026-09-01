import uuid
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field, model_validator


class CreateCaregiverLinkRequest(BaseModel):
    phone: str = Field(..., min_length=1, max_length=20, description="Phone number of caregiver")
    relationship: Optional[str] = Field(
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
    relationship: Optional[str] = None
    link_code: Optional[str] = None
    telegram_deep_link: Optional[str] = None
    status: str
    telegram_bound_at: Optional[datetime] = None
    last_message_sent_at: Optional[datetime] = None
    created_at: datetime
