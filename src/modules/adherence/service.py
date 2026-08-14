import logging
import math
import uuid
from datetime import date, datetime, time, timedelta, timezone as dt_timezone
from typing import Optional
from zoneinfo import ZoneInfo

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.common.exceptions import (
    ConflictException,
    ForbiddenException,
    NotFoundException,
    ValidationException,
)
from src.common.schemas import PageResponse
from src.modules.admin.repository import AuditLogRepository
from src.modules.adherence.repository import (
    AdherenceLogRepository,
    AlertRepository,
    HealthSurveyRepository,
)
from src.modules.adherence.schemas import (
    AdherenceLogDetailResponse,
    AdherenceSummaryResponse,
    AlertDetailResponse,
    HealthSurveyDetailResponse,
    RecordDoseActionRequest,
    ResolveAlertRequest,
    SubmitHealthSurveyRequest,
    TriggerSosRequest,
)
from src.modules.patients.repository import PatientRepository

logger = logging.getLogger(__name__)

_DEFAULT_SNOOZE_MINUTES = 15
_SEVERE_SYMPTOM_ALERT_TYPE = "RED_ALERT"
_SEVERE_SYMPTOM_ALERT_SEVERITY = "HIGH"


class AdherenceLogService:
    """Service handling dose-action logging (TAKEN/SNOOZE/SKIPPED) and
    adherence reporting. Idempotency-Key is required on record_dose_action —
    a retried/duplicate-delivered request must not double-log or re-flip
    dose state."""

    def __init__(
        self,
        db: AsyncSession,
        adherence_log_repository: AdherenceLogRepository,
    ) -> None:
        self._db = db
        self._repo = adherence_log_repository

    @staticmethod
    def _resolve_snooze_minutes(payload: dict) -> int:
        raw = payload.get("snooze_duration_minutes")
        if raw is None:
            return _DEFAULT_SNOOZE_MINUTES
        try:
            minutes = int(raw)
        except (TypeError, ValueError):
            raise ValidationException(message="snooze_duration_minutes must be an integer")
        if minutes <= 0:
            raise ValidationException(message="snooze_duration_minutes must be positive")
        return minutes

    async def record_dose_action(
        self,
        scheduled_dose_id: uuid.UUID,
        request: RecordDoseActionRequest,
        actor_payload: dict,
        idempotency_key: Optional[str],
    ) -> AdherenceLogDetailResponse:
        """PATIENT only, scoped to the dose's own patient.

        The idempotency-key lookup MUST happen before the CAS, not after: by
        the time a retry arrives, the first successful call has already
        flipped the dose out of PENDING, so a post-CAS "duplicate key ->
        IntegrityError" check would never be reached — the CAS itself
        returns None first (dose no longer PENDING) and a retry would
        incorrectly surface as 409 Conflict instead of replaying the
        original result. Checking first means a genuine replay short-circuits
        before touching the dose at all.

        1. CAS-update the ScheduledDose row (PENDING -> TAKEN/SKIPPED, or
           PENDING -> PENDING with a shifted time for SNOOZE) — single
           statement, no read-then-write race window.
        2. Insert the AdherenceLog row in the same transaction.
        The IntegrityError catch below remains as a race-safety net: two
        concurrent requests carrying the same brand-new key can both pass
        the pre-check before either commits — the loser's insert collides on
        the unique idempotency_key and its transaction (CAS included) rolls
        back, then it re-reads and returns the winner's row.
        """
        actor_id = uuid.UUID(actor_payload["sub"])
        if not idempotency_key or not idempotency_key.strip():
            raise ValidationException(message="Idempotency-Key header is required")

        existing_log = await self._repo.get_log_by_idempotency_key(idempotency_key)
        if existing_log is not None:
            return AdherenceLogDetailResponse.model_validate(existing_log)
        if self._db.in_transaction():
            # Autobegin trap (CLAUDE.md): the SELECT above autobegins an
            # implicit transaction; commit() closes it (nothing was written)
            # so the explicit begin() below doesn't raise "A transaction is
            # already begun on this Session".
            await self._db.commit()

        snooze_minutes = (
            self._resolve_snooze_minutes(request.payload)
            if request.action == "SNOOZE"
            else None
        )

        try:
            async with self._db.begin():
                dose = await self._repo.apply_dose_action_cas(
                    scheduled_dose_id, actor_id, request.action, snooze_minutes
                )
                if dose is None:
                    existing_dose = await self._repo.get_dose_scoped(
                        scheduled_dose_id, actor_id
                    )
                    if existing_dose is None:
                        raise NotFoundException(message="Scheduled dose not found")
                    raise ConflictException(message="Scheduled dose is no longer pending")

                log = await self._repo.insert_log(
                    patient_id=actor_id,
                    action=request.action,
                    action_source=request.action_source,
                    payload=request.payload,
                    idempotency_key=idempotency_key,
                    scheduled_dose_id=dose.id,
                )
        except IntegrityError:
            existing_log = await self._repo.get_log_by_idempotency_key(idempotency_key)
            if existing_log is not None:
                return AdherenceLogDetailResponse.model_validate(existing_log)
            raise

        return AdherenceLogDetailResponse.model_validate(log)

    async def get_adherence_summary(
        self,
        patient_id: uuid.UUID,
        actor_payload: dict,
        from_date: date,
        to_date: date,
    ) -> AdherenceSummaryResponse:
        """PATIENT/DOCTOR/CAREGIVER, role-agnostic access. No access -> a
        zero-filled summary (list-style filtering, matches
        SchedulingService.get_schedule), not a 404 — avoids leaking which
        patient UUIDs exist. from/to are local calendar dates in the
        patient's own timezone, converted to a single UTC range so the
        aggregate query only reads current_scheduled_at once."""
        actor_id = uuid.UUID(actor_payload["sub"])

        patient_timezone = await self._repo.get_patient_timezone_scoped(patient_id, actor_id)
        if patient_timezone is None:
            return AdherenceSummaryResponse(
                patient_id=patient_id,
                from_date=from_date,
                to_date=to_date,
                adherence_rate=0.0,
                total_doses=0,
                taken_doses=0,
                skipped_doses=0,
                missed_doses=0,
            )

        tz = ZoneInfo(patient_timezone)
        range_start = datetime.combine(from_date, time.min, tzinfo=tz).astimezone(dt_timezone.utc)
        range_end = datetime.combine(
            to_date + timedelta(days=1), time.min, tzinfo=tz
        ).astimezone(dt_timezone.utc)

        total, taken, skipped, missed = await self._repo.get_dose_status_counts(
            patient_id, actor_id, range_start, range_end
        )
        rate = round((taken / total) * 100.0, 2) if total > 0 else 0.0

        return AdherenceSummaryResponse(
            patient_id=patient_id,
            from_date=from_date,
            to_date=to_date,
            adherence_rate=rate,
            total_doses=total,
            taken_doses=taken,
            skipped_doses=skipped,
            missed_doses=missed,
        )

    async def list_adherence_logs(
        self,
        patient_id: uuid.UUID,
        actor_payload: dict,
        from_date: date,
        to_date: date,
        page: int = 1,
        size: int = 10,
    ) -> PageResponse[AdherenceLogDetailResponse]:
        """PATIENT/DOCTOR/CAREGIVER, same access + date-range handling as
        get_adherence_summary. No access -> empty page."""
        actor_id = uuid.UUID(actor_payload["sub"])

        patient_timezone = await self._repo.get_patient_timezone_scoped(patient_id, actor_id)
        if patient_timezone is None:
            return PageResponse(
                content=[], page_no=page, page_size=size, total_elements=0,
                total_pages=0, last=True,
            )

        tz = ZoneInfo(patient_timezone)
        range_start = datetime.combine(from_date, time.min, tzinfo=tz).astimezone(dt_timezone.utc)
        range_end = datetime.combine(
            to_date + timedelta(days=1), time.min, tzinfo=tz
        ).astimezone(dt_timezone.utc)

        rows, total_count = await self._repo.list_by_patient(
            patient_id, actor_id, range_start, range_end, page=page, size=size
        )

        total_pages = math.ceil(total_count / size) if total_count > 0 else 0
        last = page >= total_pages if total_pages > 0 else True
        content = [AdherenceLogDetailResponse.model_validate(r) for r in rows]

        return PageResponse(
            content=content, page_no=page, page_size=size,
            total_elements=total_count, total_pages=total_pages, last=last,
        )


class HealthSurveyService:
    """Service handling daily health survey submission. A SEVERE symptom in
    the submission auto-raises a safety Alert (triggered_by_type=
    SEVERE_SYMPTOM) in the same transaction as the survey/symptom rows —
    confirmed product behavior, not inferred from the contract doc alone."""

    def __init__(
        self,
        db: AsyncSession,
        health_survey_repository: HealthSurveyRepository,
        alert_repository: AlertRepository,
        patient_repository: Optional[PatientRepository] = None,
    ) -> None:
        self._db = db
        self._survey_repo = health_survey_repository
        self._alert_repo = alert_repository
        self._patient_repo = patient_repository or PatientRepository(db)

    async def submit_health_survey(
        self,
        patient_id: uuid.UUID,
        request: SubmitHealthSurveyRequest,
        actor_payload: dict,
    ) -> HealthSurveyDetailResponse:
        """PATIENT only, scoped to their own patient_id."""
        actor_id = uuid.UUID(actor_payload["sub"])
        if actor_id != patient_id:
            raise ForbiddenException(message="Cannot submit a survey for another patient")

        patient_row = await self._patient_repo.get_patient_with_user(patient_id)
        if patient_row is None:
            raise NotFoundException(message="Patient not found")
        if self._db.in_transaction():
            # Autobegin trap (CLAUDE.md): the SELECT above autobegins an
            # implicit transaction; commit() closes it (nothing was written)
            # so the explicit begin() below doesn't raise "A transaction is
            # already begun on this Session".
            await self._db.commit()

        severe_codes = [s.symptom_code for s in request.symptoms if s.severity == "SEVERE"]

        async with self._db.begin():
            survey = await self._survey_repo.create_survey(
                patient_id, request.survey_date, request.answers_json
            )
            symptom_dicts = [s.model_dump() for s in request.symptoms]
            await self._survey_repo.bulk_create_symptom_reports(
                patient_id, survey.id, symptom_dicts
            )
            if severe_codes:
                await self._alert_repo.create_alert(
                    patient_id=patient_id,
                    triggered_by_type="SEVERE_SYMPTOM",
                    triggered_by_id=survey.id,
                    alert_type=_SEVERE_SYMPTOM_ALERT_TYPE,
                    severity=_SEVERE_SYMPTOM_ALERT_SEVERITY,
                    message=f"Severe symptom(s) reported: {', '.join(severe_codes)}",
                )

        return HealthSurveyDetailResponse.model_validate(survey)


class AlertService:
    """Service handling SOS triggers and doctor-side alert acknowledge/resolve/list."""

    def __init__(
        self,
        db: AsyncSession,
        alert_repository: AlertRepository,
        audit_repository: AuditLogRepository,
        patient_repository: Optional[PatientRepository] = None,
    ) -> None:
        self._db = db
        self._alert_repo = alert_repository
        self._audit_repo = audit_repository
        self._patient_repo = patient_repository or PatientRepository(db)

    async def trigger_sos(
        self,
        patient_id: uuid.UUID,
        request: TriggerSosRequest,
        actor_payload: dict,
        idempotency_key: Optional[str],
    ) -> AlertDetailResponse:
        """PATIENT only, scoped to their own patient_id. Idempotency-Key is
        required — a retried/duplicate-delivered SOS tap must not page a
        doctor twice."""
        actor_id = uuid.UUID(actor_payload["sub"])
        if actor_id != patient_id:
            raise ForbiddenException(message="Cannot trigger SOS for another patient")
        if not idempotency_key or not idempotency_key.strip():
            raise ValidationException(message="Idempotency-Key header is required")

        patient_row = await self._patient_repo.get_patient_with_user(patient_id)
        if patient_row is None:
            raise NotFoundException(message="Patient not found")
        if self._db.in_transaction():
            await self._db.commit()

        try:
            async with self._db.begin():
                alert = await self._alert_repo.create_alert(
                    patient_id=patient_id,
                    triggered_by_type=request.triggered_by_type,
                    alert_type="RED_ALERT",
                    severity=request.severity,
                    message=request.message,
                    metadata=request.metadata,
                    idempotency_key=idempotency_key,
                )
        except IntegrityError:
            existing = await self._alert_repo.get_by_idempotency_key(idempotency_key)
            if existing is not None:
                return AlertDetailResponse.model_validate(existing)
            raise

        return AlertDetailResponse.model_validate(alert)

    async def acknowledge_alert(
        self,
        alert_id: uuid.UUID,
        actor_payload: dict,
        ip_address: Optional[str] = None,
    ) -> AlertDetailResponse:
        """DOCTOR only. OPEN -> ACKNOWLEDGED, assigns the acknowledging doctor."""
        doctor_id = uuid.UUID(actor_payload["sub"])

        async with self._db.begin():
            alert = await self._alert_repo.acknowledge_if_open(alert_id, doctor_id)
            if alert is None:
                await self._raise_not_found_or_conflict(alert_id)
            await self._audit_repo.create_audit_log(
                action="ACKNOWLEDGE_ALERT",
                entity_type="ALERT",
                actor_user_id=doctor_id,
                entity_id=alert_id,
                new_values={"status": "ACKNOWLEDGED"},
                ip_address=ip_address,
            )

        return AlertDetailResponse.model_validate(alert)

    async def resolve_alert(
        self,
        alert_id: uuid.UUID,
        request: ResolveAlertRequest,
        actor_payload: dict,
        ip_address: Optional[str] = None,
    ) -> AlertDetailResponse:
        """DOCTOR only. OPEN/ACKNOWLEDGED -> RESOLVED. resolution_note has no
        dedicated column on alerts — persisted via AuditLog.new_values, same
        pattern as PrescriptionService.cancel_prescription's cancel_reason."""
        doctor_id = uuid.UUID(actor_payload["sub"])

        async with self._db.begin():
            alert = await self._alert_repo.resolve_if_active(alert_id, doctor_id)
            if alert is None:
                await self._raise_not_found_or_conflict(alert_id, already="resolved")
            await self._audit_repo.create_audit_log(
                action="RESOLVE_ALERT",
                entity_type="ALERT",
                actor_user_id=doctor_id,
                entity_id=alert_id,
                new_values={
                    "status": "RESOLVED",
                    "resolution_note": request.resolution_note,
                },
                ip_address=ip_address,
            )

        return AlertDetailResponse.model_validate(alert)

    async def _raise_not_found_or_conflict(
        self, alert_id: uuid.UUID, already: Optional[str] = None
    ) -> None:
        """Disambiguate why a conditional state-transition UPDATE matched no
        row: either the alert doesn't exist (404) or it exists but is
        already past the state this action requires (409)."""
        existing = await self._alert_repo.get_by_id(alert_id)
        if existing is None:
            raise NotFoundException(message="Alert not found")
        raise ConflictException(
            message=f"Alert is already {already or existing.status.lower()}"
        )

    async def list_alerts(
        self,
        status: Optional[str] = None,
        patient_id: Optional[uuid.UUID] = None,
        page: int = 1,
        size: int = 10,
    ) -> PageResponse[AlertDetailResponse]:
        """DOCTOR/ADMIN only, platform-wide (no per-patient ownership scoping
        in the contract for this endpoint)."""
        rows, total_count = await self._alert_repo.list_alerts(
            status=status, patient_id=patient_id, page=page, size=size
        )

        total_pages = math.ceil(total_count / size) if total_count > 0 else 0
        last = page >= total_pages if total_pages > 0 else True
        content = [AlertDetailResponse.model_validate(a) for a in rows]

        return PageResponse(
            content=content, page_no=page, page_size=size,
            total_elements=total_count, total_pages=total_pages, last=last,
        )
