import uuid
from pydantic import BaseModel, ConfigDict
from typing import Optional


class MedicationDetailResponse(BaseModel):
    """Response schema for a single medication catalog entry.

    Used by: GET /medications, GET /medications/{id}.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    composition: Optional[str] = None
    manufacturer: Optional[str] = None
    uses: Optional[str] = None
    side_effects: Optional[str] = None
    image_url: Optional[str] = None
    source_name: str
    is_active: bool
