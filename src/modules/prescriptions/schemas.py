import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class MedicationDetailResponse(BaseModel):
    """Response schema for a single medication catalog entry.

    Used by: GET /medications, GET /medications/{id}.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    composition: str | None = None
    manufacturer: str | None = None
    uses: str | None = None
    side_effects: str | None = None
    image_url: str | None = None
    source_name: str
    is_active: bool


class PrescriptionItemBase(BaseModel):
    """Shared dosing-rule fields for Create/Update PrescriptionItem requests.

    No display_name here: the service resolves it from Medication.name at
    write time and freezes it onto the row as a snapshot (medication_id
    carries no FK, so later edits/deletes of the catalog entry never touch
    already-written items).
    """

    medication_id: uuid.UUID
    dose_unit: str = Field(..., max_length=30)
    morning_dose: Decimal | None = None
    noon_dose: Decimal | None = None
    evening_dose: Decimal | None = None
    bedtime_dose: Decimal | None = None
    route: str = Field(default="ORAL", max_length=30)
    meal_relation: str | None = Field(None, max_length=30)
    minimum_interval_minutes: int | None = None
    start_date: date
    end_date: date | None = None
    instructions: str | None = None
    # Doctor-set on high-risk medications: narrows the missed-dose-streak
    # fast-path alert to only this item instead of every medication. See
    # docs/graded-adherence-implementation.md Stage 2.
    is_critical: bool = False


class CreatePrescriptionItemRequest(PrescriptionItemBase):
    """Request schema for a medication line item.

    Used embedded in CreatePrescriptionRequest.items, and standalone as the
    payload for POST /prescriptions/{prescription_id}/items (prescription
    MUST be status DRAFT).
    """


class UpdatePrescriptionItemRequest(PrescriptionItemBase):
    """Request schema for updating a medication line item.

    Payload for PUT /prescriptions/{prescription_id}/items/{item_id}
    (prescription MUST be status DRAFT).
    """


class CreatePrescriptionRequest(BaseModel):
    """Request schema for Doctor creating a DRAFT prescription atomically.

    Payload for POST /prescriptions. patient_id is not supplied directly —
    the patient is identified by phone (plaintext); the service finds the
    existing account or provisions a new one (find-or-create) in the same
    call. Demographic fields (name, dob, sex, emergency_note) are provided
    to ensure full patient profile data is recorded. items may be included
    here and/or added later via POST /prescriptions/{prescription_id}/items
    while still DRAFT.
    """

    phone: str = Field(..., pattern=r"^\+?[0-9]{9,15}$")
    name: str = Field(..., max_length=255)
    dob: date = Field(...)
    sex: str = Field(..., pattern=r"^(MALE|FEMALE|OTHER)$")
    emergency_note: str | None = None
    diagnosis_note: str | None = None
    items: list[CreatePrescriptionItemRequest] = Field(default_factory=list)

    @field_validator("dob")
    @classmethod
    def validate_dob_sane(cls, v: date) -> date:
        if v <= date(1900, 1, 1):
            raise ValueError("Date of birth must be after 1900-01-01")
        if v > date.today():
            raise ValueError("Date of birth cannot be in the future")
        return v


class UpdatePrescriptionRequest(BaseModel):
    """Request schema for Doctor updating a DRAFT prescription's diagnosis.

    Payload for PUT /prescriptions/{prescription_id}.
    """

    diagnosis_note: str | None = None


class CancelPrescriptionRequest(BaseModel):
    """Request schema for Doctor cancelling a prescription."""

    cancel_reason: str = Field(..., min_length=1)


class PrescriptionItemDetailResponse(BaseModel):
    """Response schema representing a single prescription line item.

    Embedded inside PrescriptionDetailResponse.items; also returned directly
    by POST/PUT .../items(/{item_id}).
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    prescription_id: uuid.UUID
    medication_id: uuid.UUID | None = None
    display_name: str
    dose_unit: str
    morning_dose: Decimal | None = None
    noon_dose: Decimal | None = None
    evening_dose: Decimal | None = None
    bedtime_dose: Decimal | None = None
    route: str
    meal_relation: str | None = None
    minimum_interval_minutes: int | None = None
    start_date: date
    end_date: date | None = None
    instructions: str | None = None
    is_critical: bool = False
    created_at: datetime


class CurrentMedicationListResponse(BaseModel):
    """Currently active medicines from the authenticated patient's approved prescriptions."""

    as_of: date
    medications: list[PrescriptionItemDetailResponse] = Field(default_factory=list)


class PrescriptionDetailResponse(BaseModel):
    """Response schema representing a full prescription with its line items.

    Used by: GET/PUT /prescriptions/{prescription_id}, .../approve,
    .../cancel, GET /patients/{patient_id}/prescriptions. Also embedded
    inside CreatePrescriptionResponse for POST /prescriptions.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    patient_id: uuid.UUID
    doctor_id: uuid.UUID | None = None
    status: str
    diagnosis_note: str | None = None
    approved_at: datetime | None = None
    created_at: datetime
    items: list[PrescriptionItemDetailResponse] = Field(default_factory=list)


class CreatePrescriptionResponse(BaseModel):
    """Response schema for POST /prescriptions.

    Wraps PrescriptionDetailResponse with a one-time temp_password field,
    mirroring CreatePatientResponse/CaregiverLinkDetailResponse — null unless
    this call just provisioned a new patient account (phone not registered
    yet).
    """

    prescription: PrescriptionDetailResponse
    temp_password: str | None = None
