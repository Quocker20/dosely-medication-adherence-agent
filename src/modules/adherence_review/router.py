import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_db, require_roles
from src.core.celery_app import celery_app
from src.core.response import success_response
from src.modules.adherence_review.repository import AdherenceReviewRepository
from src.modules.adherence_review.service import AdherenceReviewQueryService

_SCAN_TASK_NAME = "adherence_review.scan"

adherence_reviews_router = APIRouter(prefix="/patients", tags=["Adherence Logging & Safety Alerts"])
admin_adherence_reviews_router = APIRouter(prefix="/admin/adherence-reviews", tags=["Admin & Doctor Management"])

AdherenceReaderDep = Annotated[dict, Depends(require_roles("PATIENT", "DOCTOR", "CAREGIVER"))]
AdminUserDep = Annotated[dict, Depends(require_roles("ADMIN"))]


def get_adherence_review_query_service(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AdherenceReviewQueryService:
    return AdherenceReviewQueryService(db=db, review_repository=AdherenceReviewRepository(db))


AdherenceReviewQueryServiceDep = Annotated[
    AdherenceReviewQueryService, Depends(get_adherence_review_query_service)
]


@adherence_reviews_router.get("/{patient_id}/adherence-reviews")
async def list_patient_adherence_reviews(
    patient_id: uuid.UUID,
    current_user: AdherenceReaderDep,
    service: AdherenceReviewQueryServiceDep,
    page: int = Query(1, ge=1, le=1000, description="Page number"),
    size: int = Query(10, ge=1, le=100, description="Items per page"),
) -> JSONResponse:
    """Fetch a patient's nightly graded-adherence review history, newest
    first. Same access derivation as adherence logs and health surveys
    (self / doctor-prescribed / active-caregiver) -- out-of-scope returns an
    empty page, not a 404, so the endpoint cannot be used to probe which
    patient UUIDs exist."""
    result = await service.list_patient_reviews(
        patient_id=patient_id, actor_payload=current_user, page=page, size=size
    )
    return success_response(
        data=result.model_dump(mode="json"),
        message="Adherence reviews fetched successfully",
    )


@admin_adherence_reviews_router.post("/run", status_code=status.HTTP_202_ACCEPTED)
async def trigger_adherence_review_run(current_user: AdminUserDep) -> JSONResponse:
    """ADMIN only. Enqueues the same Celery task the nightly Beat schedule
    fires, out-of-band -- needed to exercise the pipeline without waiting
    for adherence_review_run_hour. Fired by name, not by importing tasks.py
    directly, matching AutoscheduleService._dispatch_generate's reasoning:
    keeps this router free of a load-time dependency on the Celery task
    decorator and its own import chain (asyncpg engine, indicator/review
    repositories)."""
    celery_app.send_task(_SCAN_TASK_NAME)
    return success_response(
        data={"task": _SCAN_TASK_NAME},
        message="Adherence review run started",
        code=status.HTTP_202_ACCEPTED,
    )
