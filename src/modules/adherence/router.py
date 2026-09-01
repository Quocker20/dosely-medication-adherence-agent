import uuid
from datetime import date
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Header, Query, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_db, require_roles
from src.common.http import get_client_ip
from src.core.response import success_response
from src.modules.adherence.repository import (
    AdherenceLogRepository,
    AlertRepository,
    HealthSurveyRepository,
)
from src.modules.adherence.schemas import (
    BatchRecordDoseActionRequest,
    RecordDoseActionRequest,
    ResolveAlertRequest,
    SubmitHealthSurveyRequest,
    TriggerSosRequest,
)
from src.modules.adherence.service import AdherenceLogService, AlertService, HealthSurveyService
from src.modules.admin.repository import AuditLogRepository
from src.modules.patients.repository import PatientRepository


def get_adherence_log_service(db: Annotated[AsyncSession, Depends(get_db)]) -> AdherenceLogService:
    """Dependency factory providing AdherenceLogService instance."""
    return AdherenceLogService(db=db, adherence_log_repository=AdherenceLogRepository(db))


def get_health_survey_service(db: Annotated[AsyncSession, Depends(get_db)]) -> HealthSurveyService:
    """Dependency factory providing HealthSurveyService instance."""
    return HealthSurveyService(
        db=db,
        health_survey_repository=HealthSurveyRepository(db),
        alert_repository=AlertRepository(db),
        patient_repository=PatientRepository(db),
    )


def get_alert_service(db: Annotated[AsyncSession, Depends(get_db)]) -> AlertService:
    """Dependency factory providing AlertService instance."""
    return AlertService(
        db=db,
        alert_repository=AlertRepository(db),
        audit_repository=AuditLogRepository(db),
        patient_repository=PatientRepository(db),
    )


AdherenceLogServiceDep = Annotated[AdherenceLogService, Depends(get_adherence_log_service)]
HealthSurveyServiceDep = Annotated[HealthSurveyService, Depends(get_health_survey_service)]
AlertServiceDep = Annotated[AlertService, Depends(get_alert_service)]

PatientUserDep = Annotated[dict, Depends(require_roles("PATIENT"))]
DoctorUserDep = Annotated[dict, Depends(require_roles("DOCTOR"))]
DoctorOrAdminUserDep = Annotated[dict, Depends(require_roles("DOCTOR", "ADMIN"))]
# Adherence read access is role-agnostic (self / doctor-prescribed
# are independent facts checked in the service layer) -- RBAC here only narrows to
# the roles the contract lists; out-of-scope callers still get an empty
# result from the service, not a 403.
AdherenceReaderDep = Annotated[dict, Depends(require_roles("PATIENT", "DOCTOR"))]

dose_actions_router = APIRouter(tags=["Adherence Logging & Safety Alerts"])
patients_adherence_router = APIRouter(prefix="/patients", tags=["Adherence Logging & Safety Alerts"])
alerts_router = APIRouter(prefix="/alerts", tags=["Adherence Logging & Safety Alerts"])
health_surveys_router = APIRouter(
    prefix="/health-surveys", tags=["Adherence Logging & Safety Alerts"]
)


@dose_actions_router.post("/scheduled-doses/{scheduled_dose_id}/actions", status_code=status.HTTP_201_CREATED)
async def record_dose_action(
    scheduled_dose_id: uuid.UUID,
    request_body: RecordDoseActionRequest,
    current_user: PatientUserDep,
    service: AdherenceLogServiceDep,
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
) -> JSONResponse:
    """Record a dose-intake action (TAKEN/SNOOZE/SKIPPED), Patient only,
    scoped to the dose's own patient. Idempotency-Key header is required —
    a retried/duplicate-delivered request replays the original result
    instead of double-logging or re-flipping dose state."""
    result = await service.record_dose_action(
        scheduled_dose_id=scheduled_dose_id,
        request=request_body,
        actor_payload=current_user,
        idempotency_key=idempotency_key,
    )
    return success_response(
        data=result.model_dump(mode="json"),
        message="Dose action recorded successfully",
        code=status.HTTP_201_CREATED,
    )


@dose_actions_router.post("/scheduled-doses/batch-actions", status_code=status.HTTP_201_CREATED)
async def batch_record_dose_action(
    request_body: BatchRecordDoseActionRequest,
    current_user: PatientUserDep,
    service: AdherenceLogServiceDep,
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
) -> JSONResponse:
    """Record synchronized dose-intake actions across multiple doses (TAKEN/SNOOZE/SKIPPED),
    Patient only, scoped to the patient's own doses. Idempotency-Key header is required."""
    result = await service.batch_record_dose_action(
        request=request_body,
        actor_payload=current_user,
        idempotency_key=idempotency_key,
    )
    return success_response(
        data=result.model_dump(mode="json"),
        message="Batch dose actions recorded successfully",
        code=status.HTTP_201_CREATED,
    )


@patients_adherence_router.get("/{patient_id}/adherence")
async def get_adherence_summary(
    patient_id: uuid.UUID,
    current_user: AdherenceReaderDep,
    service: AdherenceLogServiceDep,
    from_date: date = Query(..., alias="from"),
    to_date: date = Query(..., alias="to"),
) -> JSONResponse:
    """Fetch adherence rate/counts for a patient over [from, to]. Access is
    role-agnostic: self-owned, doctor-prescribed, or active-caregiver-linked
    — out-of-scope returns a zero-filled summary, not 404."""
    result = await service.get_adherence_summary(
        patient_id=patient_id, actor_payload=current_user, from_date=from_date, to_date=to_date
    )
    return success_response(
        data=result.model_dump(mode="json"),
        message="Adherence summary fetched successfully",
    )


@patients_adherence_router.get("/{patient_id}/adherence/logs")
async def list_adherence_logs(
    patient_id: uuid.UUID,
    current_user: AdherenceReaderDep,
    service: AdherenceLogServiceDep,
    from_date: date = Query(..., alias="from"),
    to_date: date = Query(..., alias="to"),
    page: int = Query(1, ge=1, le=1000, description="Page number"),
    size: int = Query(10, ge=1, le=100, description="Items per page"),
) -> JSONResponse:
    """Fetch paginated raw adherence logs for a patient over [from, to].
    Same access derivation as get_adherence_summary — out-of-scope returns
    an empty page."""
    result = await service.list_adherence_logs(
        patient_id=patient_id,
        actor_payload=current_user,
        from_date=from_date,
        to_date=to_date,
        page=page,
        size=size,
    )
    return success_response(
        data=result.model_dump(mode="json"),
        message="Adherence logs fetched successfully",
    )


@patients_adherence_router.post("/{patient_id}/health-surveys", status_code=status.HTTP_201_CREATED)
async def submit_health_survey(
    patient_id: uuid.UUID,
    request_body: SubmitHealthSurveyRequest,
    current_user: PatientUserDep,
    service: HealthSurveyServiceDep,
) -> JSONResponse:
    """Submit a daily health survey (Patient only, self). A SEVERE symptom in
    the submission auto-raises a safety Alert in the same transaction."""
    result = await service.submit_health_survey(patient_id=patient_id, request=request_body, actor_payload=current_user)
    return success_response(
        data=result.model_dump(mode="json"),
        message="Health survey submitted successfully",
        code=status.HTTP_201_CREATED,
    )


@patients_adherence_router.get("/{patient_id}/health-surveys")
async def list_patient_health_surveys(
    patient_id: uuid.UUID,
    current_user: AdherenceReaderDep,
    service: HealthSurveyServiceDep,
    from_date: date = Query(..., alias="from"),
    to_date: date = Query(..., alias="to"),
    page: int = Query(1, ge=1, le=1000, description="Page number"),
    size: int = Query(10, ge=1, le=100, description="Items per page"),
) -> JSONResponse:
    """Fetch paginated health survey summaries for a patient over [from, to].
    Same access derivation as get_adherence_summary — out-of-scope returns
    an empty page."""
    result = await service.list_patient_surveys(
        patient_id=patient_id,
        actor_payload=current_user,
        from_date=from_date,
        to_date=to_date,
        page=page,
        size=size,
    )
    return success_response(
        data=result.model_dump(mode="json"),
        message="Patient health surveys fetched successfully",
    )


@patients_adherence_router.post("/{patient_id}/sos", status_code=status.HTTP_201_CREATED)
async def trigger_sos(
    patient_id: uuid.UUID,
    request_body: TriggerSosRequest,
    current_user: PatientUserDep,
    service: AlertServiceDep,
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
) -> JSONResponse:
    """Trigger an emergency SOS alert (Patient only, self). Idempotency-Key
    header is required — a retried/duplicate-delivered tap must not page a
    doctor with two CRITICAL alerts."""
    result = await service.trigger_sos(
        patient_id=patient_id,
        request=request_body,
        actor_payload=current_user,
        idempotency_key=idempotency_key,
    )
    return success_response(
        data=result.model_dump(mode="json"),
        message="SOS alert triggered successfully",
        code=status.HTTP_201_CREATED,
    )


@health_surveys_router.get("")
async def list_health_surveys(
    current_user: DoctorOrAdminUserDep,
    service: HealthSurveyServiceDep,
    from_date: date = Query(..., alias="from"),
    to_date: date = Query(..., alias="to"),
    patient_id: Optional[uuid.UUID] = Query(None, alias="patientId"),
    severity: Optional[str] = Query(
        None, pattern=r"^(MILD|MODERATE|SEVERE)$"
    ),
    page: int = Query(1, ge=1, le=1000, description="Page number"),
    size: int = Query(10, ge=1, le=100, description="Items per page"),
) -> JSONResponse:
    """Doctor dashboard health survey list (Doctor/Admin only). Doctor is
    scoped to patients they've written at least one prescription for; Admin
    is platform-wide."""
    result = await service.list_surveys(
        actor_payload=current_user,
        from_date=from_date,
        to_date=to_date,
        patient_id=patient_id,
        severity=severity,
        page=page,
        size=size,
    )
    return success_response(
        data=result.model_dump(mode="json"),
        message="Health survey list fetched successfully",
    )


@health_surveys_router.get("/{survey_id}")
async def get_health_survey(
    survey_id: uuid.UUID,
    current_user: AdherenceReaderDep,
    service: HealthSurveyServiceDep,
) -> JSONResponse:
    """Fetch one health survey with its full answers and symptom list.
    Access is role-agnostic: self-owned, doctor-prescribed, or
    active-caregiver-linked — anything else (including nonexistent) is 404."""
    result = await service.get_survey_detail(survey_id=survey_id, actor_payload=current_user)
    return success_response(
        data=result.model_dump(mode="json"),
        message="Health survey fetched successfully",
    )


@alerts_router.get("")
async def list_alerts(
    current_user: DoctorOrAdminUserDep,
    service: AlertServiceDep,
    status_filter: Optional[str] = Query(None, alias="status", pattern=r"^(OPEN|ACKNOWLEDGED|RESOLVED)$"),
    patient_id: Optional[uuid.UUID] = Query(None, alias="patientId"),
    page: int = Query(1, ge=1, le=1000, description="Page number"),
    size: int = Query(10, ge=1, le=100, description="Items per page"),
) -> JSONResponse:
    """Doctor dashboard alerts list (Doctor/Admin only), platform-wide."""
    result = await service.list_alerts(status=status_filter, patient_id=patient_id, page=page, size=size)
    return success_response(
        data=result.model_dump(mode="json"),
        message="Alert list fetched successfully",
    )


@alerts_router.post("/{alert_id}/acknowledge")
async def acknowledge_alert(
    alert_id: uuid.UUID,
    raw_request: Request,
    current_user: DoctorUserDep,
    service: AlertServiceDep,
) -> JSONResponse:
    """Acknowledge an OPEN alert (Doctor only); assigns the acknowledging doctor."""
    ip_address = get_client_ip(raw_request)
    result = await service.acknowledge_alert(alert_id=alert_id, actor_payload=current_user, ip_address=ip_address)
    return success_response(
        data=result.model_dump(mode="json"),
        message="Alert acknowledged successfully",
    )


@alerts_router.post("/{alert_id}/resolve")
async def resolve_alert(
    alert_id: uuid.UUID,
    request_body: ResolveAlertRequest,
    raw_request: Request,
    current_user: DoctorUserDep,
    service: AlertServiceDep,
) -> JSONResponse:
    """Resolve an OPEN/ACKNOWLEDGED alert (Doctor only)."""
    ip_address = get_client_ip(raw_request)
    result = await service.resolve_alert(
        alert_id=alert_id,
        request=request_body,
        actor_payload=current_user,
        ip_address=ip_address,
    )
    return success_response(
        data=result.model_dump(mode="json"),
        message="Alert resolved successfully",
    )
