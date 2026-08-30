from __future__ import annotations

import math
import uuid
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.common.exceptions import ForbiddenException, NotFoundException
from src.common.schemas import PageResponse
from src.modules.adherence.models import Alert, SuspectedAdverseEvent
from src.modules.patients.models import PatientProfile
from src.modules.prescriptions.models import Prescription


class AdverseSymptom(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    severity: Literal["MILD", "MODERATE", "SEVERE"] = "MILD"
    onset: str | None = Field(default=None, max_length=100)
    description: str | None = Field(default=None, max_length=500)


class RelatedMedication(BaseModel):
    medication_id: uuid.UUID | None = None
    drug_name: str = Field(min_length=1, max_length=255)
    taken_at: datetime | None = None
    context_type: Literal["RECENTLY_TAKEN", "ACTIVE_PRESCRIPTION"]


class CreateAdverseEventRequest(BaseModel):
    conversation_id: uuid.UUID | None = None
    raw_text: str = Field(min_length=1, max_length=5000)
    symptoms: list[AdverseSymptom] = Field(min_length=1, max_length=10)
    related_medications: list[RelatedMedication] = Field(default_factory=list, max_length=20)
    risk_level: Literal["LOW", "MODERATE", "HIGH", "CRITICAL"]


class ReviewAdverseEventRequest(BaseModel):
    causality: Literal["UNASSESSED", "POSSIBLE", "UNLIKELY", "CONFIRMED"]
    clinician_note: str = Field(min_length=1, max_length=2000)


class AdverseEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    patient_id: uuid.UUID
    patient_name: str = ""
    conversation_id: uuid.UUID | None = None
    raw_text: str
    symptoms: list[dict[str, Any]]
    related_medications: list[dict[str, Any]]
    risk_level: str
    causality: str
    review_status: str
    source: str
    alert_id: uuid.UUID | None = None
    clinician_note: str | None = None
    reported_at: datetime
    reviewed_at: datetime | None = None


class AdverseEventRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(self, patient_id: uuid.UUID, request: CreateAdverseEventRequest) -> SuspectedAdverseEvent:
        row = SuspectedAdverseEvent(
            patient_id=patient_id, conversation_id=request.conversation_id,
            raw_text=request.raw_text,
            symptoms=[item.model_dump(mode="json") for item in request.symptoms],
            related_medications=[item.model_dump(mode="json") for item in request.related_medications],
            risk_level=request.risk_level,
        )
        self.db.add(row)
        await self.db.flush()
        return row

    async def attach_alert(self, event_id: uuid.UUID, alert_id: uuid.UUID) -> None:
        await self.db.execute(update(SuspectedAdverseEvent).where(SuspectedAdverseEvent.id == event_id).values(alert_id=alert_id))

    async def list(self, doctor_id: uuid.UUID | None, status: str | None, risk: str | None, page: int, size: int):
        filters = []
        if doctor_id:
            filters.append(select(Prescription.id).where(Prescription.doctor_id == doctor_id, Prescription.patient_id == SuspectedAdverseEvent.patient_id).exists())
        if status:
            filters.append(SuspectedAdverseEvent.review_status == status)
        if risk:
            filters.append(SuspectedAdverseEvent.risk_level == risk)
        total = (await self.db.execute(select(func.count(SuspectedAdverseEvent.id)).where(*filters))).scalar_one()
        stmt = (select(SuspectedAdverseEvent, PatientProfile.name).join(PatientProfile, PatientProfile.user_id == SuspectedAdverseEvent.patient_id)
                .where(*filters).order_by(SuspectedAdverseEvent.reported_at.desc()).offset((page-1)*size).limit(size))
        return list((await self.db.execute(stmt)).all()), total

    async def get(self, event_id: uuid.UUID) -> SuspectedAdverseEvent | None:
        return (await self.db.execute(select(SuspectedAdverseEvent).where(SuspectedAdverseEvent.id == event_id))).scalar_one_or_none()

    async def get_for_patient(self, event_id: uuid.UUID, patient_id: uuid.UUID) -> SuspectedAdverseEvent | None:
        return (await self.db.execute(select(SuspectedAdverseEvent).where(
            SuspectedAdverseEvent.id == event_id, SuspectedAdverseEvent.patient_id == patient_id
        ))).scalar_one_or_none()

    async def review(self, event_id: uuid.UUID, doctor_id: uuid.UUID, request: ReviewAdverseEventRequest):
        doctor_has_patient = select(Prescription.id).where(
            Prescription.doctor_id == doctor_id,
            Prescription.patient_id == SuspectedAdverseEvent.patient_id,
        ).exists()
        stmt = (update(SuspectedAdverseEvent).where(SuspectedAdverseEvent.id == event_id, doctor_has_patient)
                .values(review_status="REVIEWED", causality=request.causality, clinician_note=request.clinician_note,
                        reviewed_at=datetime.now(timezone.utc), reviewed_by=doctor_id).returning(SuspectedAdverseEvent))
        return (await self.db.execute(stmt)).scalar_one_or_none()


class AdverseEventService:
    def __init__(self, db: AsyncSession) -> None:
        self.db, self.repo = db, AdverseEventRepository(db)

    async def create(self, patient_id: uuid.UUID, request: CreateAdverseEventRequest, actor: dict) -> AdverseEventResponse:
        if uuid.UUID(actor["sub"]) != patient_id:
            raise ForbiddenException(message="Cannot report an event for another patient")
        async with self.db.begin():
            event = await self.repo.create(patient_id, request)
            if request.risk_level in {"HIGH", "CRITICAL"}:
                alert = Alert(patient_id=patient_id, triggered_by_type="ADVERSE_EVENT", triggered_by_id=event.id,
                              alert_type="SUSPECTED_ADVERSE_EVENT", severity=request.risk_level, status="OPEN",
                              message="Triệu chứng nghi ngờ cần bác sĩ xem ngay: " + ", ".join(s.name for s in request.symptoms),
                              alert_metadata={"adverse_event_id": str(event.id), "symptoms": event.symptoms})
                self.db.add(alert); await self.db.flush(); await self.repo.attach_alert(event.id, alert.id); event.alert_id = alert.id
        return AdverseEventResponse.model_validate(event)

    async def list(self, actor: dict, status: str | None, risk: str | None, page: int, size: int):
        doctor_id = None if actor.get("role") == "ADMIN" else uuid.UUID(actor["sub"])
        rows, total = await self.repo.list(doctor_id, status, risk, page, size)
        content = [AdverseEventResponse(**{**AdverseEventResponse.model_validate(row).model_dump(), "patient_name": name}) for row, name in rows]
        pages = math.ceil(total / size) if total else 0
        return PageResponse(content=content, page_no=page, page_size=size, total_elements=total, total_pages=pages, last=page >= pages if pages else True)

    async def get_for_patient(self, patient_id: uuid.UUID, event_id: uuid.UUID, actor: dict):
        if uuid.UUID(actor["sub"]) != patient_id:
            raise ForbiddenException(message="Cannot read another patient's event")
        event = await self.repo.get_for_patient(event_id, patient_id)
        if event is None: raise NotFoundException(message="Suspected adverse event not found")
        return AdverseEventResponse.model_validate(event)

    async def review(self, event_id: uuid.UUID, request: ReviewAdverseEventRequest, actor: dict):
        async with self.db.begin():
            event = await self.repo.review(event_id, uuid.UUID(actor["sub"]), request)
            if event is None: raise NotFoundException(message="Suspected adverse event not found")
        return AdverseEventResponse.model_validate(event)
