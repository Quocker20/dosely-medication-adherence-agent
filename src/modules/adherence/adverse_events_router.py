import uuid
from typing import Annotated
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from src.api.deps import get_db, require_roles
from src.core.response import success_response
from src.modules.adherence.adverse_events import AdverseEventService, CreateAdverseEventRequest, ReviewAdverseEventRequest

router = APIRouter(tags=["Suspected Adverse Events"])

def service(db: Annotated[AsyncSession, Depends(get_db)]) -> AdverseEventService: return AdverseEventService(db)

@router.post("/patients/{patient_id}/adverse-events", status_code=status.HTTP_201_CREATED)
async def create_event(patient_id: uuid.UUID, body: CreateAdverseEventRequest,
                       actor: Annotated[dict, Depends(require_roles("PATIENT"))],
                       svc: Annotated[AdverseEventService, Depends(service)]):
    result = await svc.create(patient_id, body, actor)
    return success_response(data=result.model_dump(mode="json"), message="Đã ghi nhận triệu chứng để bác sĩ xem xét", code=201)

@router.get("/adverse-events")
async def list_events(actor: Annotated[dict, Depends(require_roles("DOCTOR", "ADMIN"))],
                      svc: Annotated[AdverseEventService, Depends(service)],
                      review_status: str | None = Query(None, alias="status", pattern="^(NEW|ACKNOWLEDGED|REVIEWED)$"),
                      risk: str | None = Query(None, pattern="^(LOW|MODERATE|HIGH|CRITICAL)$"),
                      page: int = Query(1, ge=1), size: int = Query(50, ge=1, le=100)):
    result = await svc.list(actor, review_status, risk, page, size)
    return success_response(data=result.model_dump(mode="json"), message="Danh sách triệu chứng nghi ngờ")

@router.get("/patients/{patient_id}/adverse-events/{event_id}")
async def get_patient_event(patient_id: uuid.UUID, event_id: uuid.UUID,
                            actor: Annotated[dict, Depends(require_roles("PATIENT"))],
                            svc: Annotated[AdverseEventService, Depends(service)]):
    result = await svc.get_for_patient(patient_id, event_id, actor)
    return success_response(data=result.model_dump(mode="json"), message="Chi tiết triệu chứng nghi ngờ")

@router.post("/adverse-events/{event_id}/review")
async def review_event(event_id: uuid.UUID, body: ReviewAdverseEventRequest,
                       actor: Annotated[dict, Depends(require_roles("DOCTOR"))],
                       svc: Annotated[AdverseEventService, Depends(service)]):
    result = await svc.review(event_id, body, actor)
    return success_response(data=result.model_dump(mode="json"), message="Đã lưu đánh giá của bác sĩ")
