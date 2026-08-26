import logging
import math
import secrets
import string
import uuid
from datetime import date, datetime
from datetime import timezone as dt_timezone
from typing import Optional, Tuple

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.common.exceptions import (
    ForbiddenException,
    NotFoundException,
    ValidationException,
)
from src.common.schemas import PageResponse
from src.core.celery_app import celery_app
from src.core.config import get_settings
from src.core.security import hash_password, validate_phone_number
from src.modules.admin.repository import AuditLogRepository, DoctorRepository
from src.modules.agents.repository import ScheduledDoseRepository
from src.modules.auth.models import User
from src.modules.auth.repository import AuthRepository
from src.modules.patients.constants import DEFAULT_ROUTINE
from src.modules.patients.repository import PatientRepository
from src.modules.prescriptions.models import Prescription, PrescriptionItem
from src.modules.prescriptions.repository import MedicationRepository, PrescriptionRepository
from src.modules.prescriptions.schemas import (
    CancelPrescriptionRequest,
    CreatePrescriptionItemRequest,
    CreatePrescriptionRequest,
    CreatePrescriptionResponse,
    CurrentMedicationListResponse,
    MedicationDetailResponse,
    PrescriptionDetailResponse,
    PrescriptionItemDetailResponse,
    UpdatePrescriptionItemRequest,
    UpdatePrescriptionRequest,
)

logger = logging.getLogger(__name__)

_AUTOSCHEDULE_TASK_NAME = "agents.autoschedule"

_MUTABLE_STATUS = "DRAFT"
_CANCELLABLE_STATUSES = ("DRAFT", "APPROVED")


class MedicationService:
    """Service handling Medication catalog read operations."""

    def __init__(self, db: AsyncSession, medication_repository: MedicationRepository) -> None:
        self._db = db
        self._medication_repo = medication_repository

    async def list_medications(
        self, page: int = 1, size: int = 10, search: Optional[str] = None
    ) -> PageResponse[MedicationDetailResponse]:
        """Fetch paginated medication catalog."""
        items, total_count = await self._medication_repo.list_medications(
            page=page, size=size, search=search, active_only=True
        )

        total_pages = math.ceil(total_count / size) if total_count > 0 else 0
        last = page >= total_pages if total_pages > 0 else True

        content = [MedicationDetailResponse.model_validate(m) for m in items]

        return PageResponse(
            content=content,
            page_no=page,
            page_size=size,
            total_elements=total_count,
            total_pages=total_pages,
            last=last,
        )

    async def get_medication(self, medication_id: uuid.UUID) -> MedicationDetailResponse:
        """Fetch single medication detail by ID."""
        medication = await self._medication_repo.get_medication_by_id(medication_id)
        if medication is None:
            raise NotFoundException(message="Medication not found")
        return MedicationDetailResponse.model_validate(medication)


class PrescriptionService:
    """Service handling Prescription state machine and PrescriptionItem operations.

    HITL: only DOCTOR may create/update/approve/cancel/manage items. Items
    (add/update/delete) are only permitted while the prescription is DRAFT —
    once APPROVED or CANCELLED, its item list is locked.
    """

    def __init__(
        self,
        db: AsyncSession,
        prescription_repository: PrescriptionRepository,
        doctor_repository: DoctorRepository,
        audit_repository: AuditLogRepository,
        medication_repository: Optional[MedicationRepository] = None,
        auth_repository: Optional[AuthRepository] = None,
        patient_repository: Optional[PatientRepository] = None,
        scheduled_dose_repository: Optional[ScheduledDoseRepository] = None,
    ) -> None:
        self._db = db
        self._rx_repo = prescription_repository
        self._doctor_repo = doctor_repository
        self._audit_repo = audit_repository
        self._medication_repo = medication_repository or MedicationRepository(db)
        self._auth_repo = auth_repository or AuthRepository(db)
        self._patient_repo = patient_repository or PatientRepository(db)
        self._dose_repo = scheduled_dose_repository or ScheduledDoseRepository(db)

    @staticmethod
    def _generate_temp_pin() -> str:
        """Generate a random 6-digit PIN string."""
        return "".join(secrets.choice(string.digits) for _ in range(6))

    @staticmethod
    def _dispatch_schedule_generation(patient_id: uuid.UUID, prescription_id: uuid.UUID) -> None:
        """Start the Planning Agent once a prescription is approved — the
        PrescriptionApproved event the API spec (mục 8) calls for.

        Fail-open on purpose: approval is the doctor's clinical HITL decision
        and it is already committed. Rolling it back because a broker is down
        would be the worse failure, and the schedule can still be produced via
        POST /patients/{id}/schedules/generate. The cost of this choice is that
        an approved prescription can briefly have no reminders, which is why
        the run is retried rather than best-effort.
        """
        if not get_settings().prescription_autoschedule_enabled:
            return
        try:
            celery_app.send_task(
                _AUTOSCHEDULE_TASK_NAME,
                args=[str(patient_id), str(prescription_id), "PRESCRIPTION_APPROVED"],
            )
        except Exception:
            logger.exception(
                "Auto-schedule dispatch failed for prescription %s; approval stands",
                prescription_id,
            )

    @staticmethod
    def _to_item_detail(item: PrescriptionItem) -> PrescriptionItemDetailResponse:
        return PrescriptionItemDetailResponse.model_validate(item)

    async def _snapshot_item_fields(self, item_data: dict) -> dict:
        """Resolve medication_id -> Medication and freeze its current name
        onto display_name. No FK ties the row to medications afterward, so
        this snapshot is the only place the name is ever read from the
        catalog — later edits/deletes of the Medication row cannot affect it."""
        medication_id = item_data["medication_id"]
        medication = await self._medication_repo.get_medication_by_id(medication_id)
        if medication is None:
            raise NotFoundException(message="Medication not found")
        return {**item_data, "display_name": medication.name}

    @classmethod
    def _to_detail(
        cls, prescription: Prescription, items: list
    ) -> PrescriptionDetailResponse:
        return PrescriptionDetailResponse(
            id=prescription.id,
            patient_id=prescription.patient_id,
            doctor_id=prescription.doctor_id,
            status=prescription.status,
            diagnosis_note=prescription.diagnosis_note,
            approved_at=prescription.approved_at,
            created_at=prescription.created_at,
            items=[cls._to_item_detail(item) for item in items],
        )

    async def _resolve_or_create_patient(
        self,
        cleaned_phone: str,
        name: Optional[str] = None,
        dob: Optional[date] = None,
        sex: Optional[str] = None,
        emergency_note: Optional[str] = None,
    ) -> Tuple[User, Optional[str]]:
        """Find the patient's user account by phone, creating one with a temp
        PIN if it doesn't exist yet (same pattern as
        PatientService._resolve_or_create_caregiver).

        Patient profile demographics are populated directly if provided.

        Runs the create as its own transaction, separate from the prescription
        insert that follows: an IntegrityError here (concurrent create on the
        same new phone) would otherwise poison the outer transaction, since
        Postgres aborts the whole transaction block on any statement error.
        Catching it here and re-reading the now-existing row keeps this call
        race-safe without SAVEPOINTs.
        """
        user = await self._auth_repo.get_user_by_phone(cleaned_phone)
        if self._db.in_transaction():
            # commit(), not rollback(): ends the SELECT's autobegin transaction
            # the same way rollback() would (nothing was written either way),
            # but expire_on_commit=False on this sessionmaker means commit()
            # leaves `user`'s attributes populated. rollback() unconditionally
            # expires every object in the session regardless of that setting,
            # so a bare `user.id` access below (outside an awaited call, hence
            # outside the asyncio greenlet) would raise MissingGreenlet trying
            # to lazily reload it.
            await self._db.commit()
        if user is not None:
            return user, None

        temp_pin = self._generate_temp_pin()
        hashed_pin = hash_password(temp_pin)
        try:
            async with self._db.begin():
                user = await self._auth_repo.create_user(
                    phone=cleaned_phone,
                    hashed_password=hashed_pin,
                    role="PATIENT",
                )
                await self._patient_repo.create_patient_profile(
                    user_id=user.id,
                    name=name or "NULL",
                    dob=dob,
                    sex=sex,
                    emergency_note=emergency_note,
                )
                # Same transaction as the profile: without a routine row,
                # expand_schedule raises MissingRoutineAnchorError on the first
                # approved prescription and the run terminates at
                # NEEDS_REVIEW with zero doses. Same reasoning as
                # PatientService.create_patient.
                await self._patient_repo.upsert_routine(
                    patient_id=user.id,
                    updates=dict(DEFAULT_ROUTINE),
                )
        except IntegrityError:
            user = await self._auth_repo.get_user_by_phone(cleaned_phone)
            if self._db.in_transaction():
                await self._db.commit()
            if user is None:
                raise
            return user, None
        return user, temp_pin

    async def _raise_not_owner_or_wrong_status(
        self,
        prescription_id: uuid.UUID,
        doctor_id: uuid.UUID,
        allowed_statuses: Tuple[str, ...],
    ) -> None:
        """Disambiguate why a conditional state-transition UPDATE matched no
        row: either the prescription doesn't exist / isn't owned by this
        doctor (404 — indistinguishable, blocks UUID probing) or it exists but
        is in the wrong status to be mutated (422, per api-contract.md)."""
        existing = await self._rx_repo.get_by_id_for_doctor(prescription_id, doctor_id)
        if existing is None:
            raise NotFoundException(message="Prescription not found")
        raise ValidationException(
            message=f"Prescription must be in {'/'.join(allowed_statuses)} status for this action"
        )

    async def create_prescription(
        self,
        request: CreatePrescriptionRequest,
        actor_payload: dict,
        ip_address: Optional[str] = None,
    ) -> CreatePrescriptionResponse:
        """Doctor creates a DRAFT prescription for a patient identified by
        phone, atomically with its line items.

        1. Find-or-create the patient account by phone (own transaction).
        2. Confirm the acting doctor is still ACTIVE (token may outlive a
            deactivation — this closes most of that window, not all of it).
        3. Persist Prescription, PrescriptionItems (bulk, single flush), and
            AuditLog in one transaction.
        """
        cleaned_phone = validate_phone_number(request.phone)
        doctor_id = uuid.UUID(actor_payload["sub"])

        patient_user, temp_pin = await self._resolve_or_create_patient(
            cleaned_phone,
            name=request.name,
            dob=request.dob,
            sex=request.sex,
            emergency_note=request.emergency_note,
        )

        item_fields = [
            await self._snapshot_item_fields(item.model_dump())
            for item in request.items
        ]
        if self._db.in_transaction():
            # commit(), not rollback(): ends the SELECT's autobegin transaction
            # (nothing was written), same reasoning as _resolve_or_create_patient.
            await self._db.commit()

        async with self._db.begin():
            doctor_row = await self._doctor_repo.get_doctor_with_user(doctor_id)
            if doctor_row is None:
                raise NotFoundException(message="Doctor profile not found")
            _, doctor_user = doctor_row
            if doctor_user.status != "ACTIVE":
                raise ForbiddenException(message="Doctor account is not active")

            prescription = await self._rx_repo.create_prescription(
                patient_id=patient_user.id,
                doctor_id=doctor_id,
                diagnosis_note=request.diagnosis_note,
            )
            items = await self._rx_repo.bulk_create_items(
                prescription.id, item_fields
            )
            await self._audit_repo.create_audit_log(
                action="CREATE_PRESCRIPTION",
                entity_type="PRESCRIPTION",
                actor_user_id=doctor_id,
                entity_id=prescription.id,
                new_values={
                    "patient_id": str(patient_user.id),
                    "item_count": len(items),
                },
                ip_address=ip_address,
            )

        return CreatePrescriptionResponse(
            prescription=self._to_detail(prescription, items),
            temp_password=temp_pin,
        )

    async def get_prescription(
        self, prescription_id: uuid.UUID, actor_payload: dict
    ) -> PrescriptionDetailResponse:
        """Fetch prescription detail. Access is role-agnostic: self-owned,
        doctor-prescribed, or active-caregiver-linked — independent facts
        checked together. Out-of-scope -> 404, indistinguishable from a
        prescription that does not exist."""
        role = actor_payload.get("role")
        actor_id = None if role == "ADMIN" else uuid.UUID(actor_payload["sub"])

        prescription = await self._rx_repo.get_by_id(prescription_id, actor_id=actor_id)
        if prescription is None:
            raise NotFoundException(message="Prescription not found")
        items = await self._rx_repo.get_items(prescription_id)
        return self._to_detail(prescription, items)

    async def list_prescriptions(
        self,
        patient_id: uuid.UUID,
        actor_payload: dict,
        status: Optional[str] = None,
        page: int = 1,
        size: int = 10,
    ) -> PageResponse[PrescriptionDetailResponse]:
        """Fetch paginated prescriptions for a patient, restricted the same
        way as get_prescription (list-style filtering: out-of-scope actor
        just sees an empty page, no dedicated 404)."""
        role = actor_payload.get("role")
        actor_id = None if role == "ADMIN" else uuid.UUID(actor_payload["sub"])

        rows, total_count = await self._rx_repo.list_by_patient(
            patient_id, actor_id=actor_id, status=status, page=page, size=size
        )

        total_pages = math.ceil(total_count / size) if total_count > 0 else 0
        last = page >= total_pages if total_pages > 0 else True

        items_map = await self._rx_repo.get_items_for_prescriptions(
            [p.id for p in rows]
        )
        content = [self._to_detail(p, items_map.get(p.id, [])) for p in rows]

        return PageResponse(
            content=content,
            page_no=page,
            page_size=size,
            total_elements=total_count,
            total_pages=total_pages,
            last=last,
        )

    async def update_prescription(
        self,
        prescription_id: uuid.UUID,
        request: UpdatePrescriptionRequest,
        actor_payload: dict,
    ) -> PrescriptionDetailResponse:
        """DOCTOR only, scoped to the doctor who created it. Only permitted
        while DRAFT."""
        doctor_id = uuid.UUID(actor_payload["sub"])

        async with self._db.begin():
            prescription = await self._rx_repo.update_diagnosis_if_draft(
                prescription_id, doctor_id, request.diagnosis_note
            )
            if prescription is None:
                await self._raise_not_owner_or_wrong_status(
                    prescription_id, doctor_id, (_MUTABLE_STATUS,)
                )

        items = await self._rx_repo.get_items(prescription_id)
        return self._to_detail(prescription, items)

    async def approve_prescription(
        self,
        prescription_id: uuid.UUID,
        actor_payload: dict,
        ip_address: Optional[str] = None,
    ) -> PrescriptionDetailResponse:
        """DOCTOR only, scoped to the doctor who created it. DRAFT -> APPROVED."""
        doctor_id = uuid.UUID(actor_payload["sub"])

        async with self._db.begin():
            prescription = await self._rx_repo.approve_if_draft(prescription_id, doctor_id)
            if prescription is None:
                await self._raise_not_owner_or_wrong_status(
                    prescription_id, doctor_id, (_MUTABLE_STATUS,)
                )
            await self._audit_repo.create_audit_log(
                action="APPROVE_PRESCRIPTION",
                entity_type="PRESCRIPTION",
                actor_user_id=doctor_id,
                entity_id=prescription_id,
                new_values={"status": "APPROVED"},
                ip_address=ip_address,
            )

        items = await self._rx_repo.get_items(prescription_id)
        # After the commit: the prescription is APPROVED, so the Planning Agent
        # can now read it (it only ever reads APPROVED rows).
        self._dispatch_schedule_generation(prescription.patient_id, prescription_id)
        return self._to_detail(prescription, items)

    async def cancel_prescription(
        self,
        prescription_id: uuid.UUID,
        request: CancelPrescriptionRequest,
        actor_payload: dict,
        ip_address: Optional[str] = None,
    ) -> PrescriptionDetailResponse:
        """DOCTOR only, scoped to the doctor who created it. DRAFT/APPROVED ->
        CANCELLED. cancel_reason has no dedicated column on prescriptions —
        persisted via AuditLog.new_values, same as other admin-style actions
        (CREATE_PATIENT, ADD_CAREGIVER_LINK) that don't warrant a schema change."""
        doctor_id = uuid.UUID(actor_payload["sub"])

        async with self._db.begin():
            prescription = await self._rx_repo.cancel_if_active(prescription_id, doctor_id)
            if prescription is None:
                await self._raise_not_owner_or_wrong_status(
                    prescription_id, doctor_id, _CANCELLABLE_STATUSES
                )
            # Without this, already-generated future PENDING doses for this
            # prescription sit untouched — the missed-dose scan
            # (MissedDoseScanService) would eventually mark them MISSED and
            # raise a Red Alert for medication the patient is no longer even
            # supposed to take. Scoped to this prescription only, not the
            # whole patient — other still-active prescriptions' doses must
            # survive (unlike reschedule's delete_future_pending).
            await self._dose_repo.delete_future_pending_for_prescription(
                prescription_id, now=datetime.now(dt_timezone.utc)
            )
            await self._audit_repo.create_audit_log(
                action="CANCEL_PRESCRIPTION",
                entity_type="PRESCRIPTION",
                actor_user_id=doctor_id,
                entity_id=prescription_id,
                new_values={"status": "CANCELLED", "cancel_reason": request.cancel_reason},
                ip_address=ip_address,
            )

        items = await self._rx_repo.get_items(prescription_id)
        return self._to_detail(prescription, items)

    async def _lock_draft_or_raise(
        self, prescription_id: uuid.UUID, doctor_id: uuid.UUID
    ) -> Prescription:
        """Row-lock the prescription (FOR UPDATE) and enforce DRAFT status.
        Held for the rest of the caller's transaction, serializing against a
        concurrent approve/cancel on the same row (both take a row lock via
        their UPDATE) — whichever transaction commits first decides the
        outcome the other observes."""
        prescription = await self._rx_repo.lock_for_items(prescription_id, doctor_id)
        if prescription is None:
            raise NotFoundException(message="Prescription not found")
        if prescription.status != _MUTABLE_STATUS:
            raise ValidationException(
                message=f"Prescription must be in {_MUTABLE_STATUS} status to manage items"
            )
        return prescription

    async def add_item(
        self,
        prescription_id: uuid.UUID,
        request: CreatePrescriptionItemRequest,
        actor_payload: dict,
        ip_address: Optional[str] = None,
    ) -> PrescriptionItemDetailResponse:
        """DOCTOR only, scoped to the doctor who created the prescription.
        Prescription MUST be DRAFT."""
        doctor_id = uuid.UUID(actor_payload["sub"])
        fields = await self._snapshot_item_fields(request.model_dump())
        if self._db.in_transaction():
            # _snapshot_item_fields' SELECT autobegins an implicit transaction;
            # without closing it the begin() below raises "A transaction is
            # already begun on this Session" and the endpoint 500s on every
            # call. commit(), not rollback(): nothing was written. Same guard
            # create_prescription already carries.
            await self._db.commit()

        async with self._db.begin():
            await self._lock_draft_or_raise(prescription_id, doctor_id)
            item = await self._rx_repo.add_item(prescription_id, fields)
            await self._audit_repo.create_audit_log(
                action="ADD_PRESCRIPTION_ITEM",
                entity_type="PRESCRIPTION_ITEM",
                actor_user_id=doctor_id,
                entity_id=item.id,
                new_values={"display_name": fields["display_name"]},
                ip_address=ip_address,
            )

        return self._to_item_detail(item)

    async def update_item(
        self,
        prescription_id: uuid.UUID,
        item_id: uuid.UUID,
        request: UpdatePrescriptionItemRequest,
        actor_payload: dict,
        ip_address: Optional[str] = None,
    ) -> PrescriptionItemDetailResponse:
        """DOCTOR only, scoped to the doctor who created the prescription.
        Prescription MUST be DRAFT."""
        doctor_id = uuid.UUID(actor_payload["sub"])
        fields = await self._snapshot_item_fields(request.model_dump())
        if self._db.in_transaction():
            # Same autobegin guard as add_item — see the note there.
            await self._db.commit()

        async with self._db.begin():
            await self._lock_draft_or_raise(prescription_id, doctor_id)
            existing_item = await self._rx_repo.get_item(item_id, prescription_id)
            if existing_item is None:
                raise NotFoundException(message="Prescription item not found")

            old_display_name = existing_item.display_name
            item = await self._rx_repo.update_item(item_id, fields)
            await self._audit_repo.create_audit_log(
                action="UPDATE_PRESCRIPTION_ITEM",
                entity_type="PRESCRIPTION_ITEM",
                actor_user_id=doctor_id,
                entity_id=item_id,
                old_values={"display_name": old_display_name},
                new_values={"display_name": fields["display_name"]},
                ip_address=ip_address,
            )

        return self._to_item_detail(item)

    async def delete_item(
        self,
        prescription_id: uuid.UUID,
        item_id: uuid.UUID,
        actor_payload: dict,
        ip_address: Optional[str] = None,
    ) -> None:
        """DOCTOR only, scoped to the doctor who created the prescription.
        Prescription MUST be DRAFT. Hard delete."""
        doctor_id = uuid.UUID(actor_payload["sub"])

        async with self._db.begin():
            await self._lock_draft_or_raise(prescription_id, doctor_id)
            existing_item = await self._rx_repo.get_item(item_id, prescription_id)
            if existing_item is None:
                raise NotFoundException(message="Prescription item not found")

            await self._rx_repo.delete_item(item_id)
            await self._audit_repo.create_audit_log(
                action="DELETE_PRESCRIPTION_ITEM",
                entity_type="PRESCRIPTION_ITEM",
                actor_user_id=doctor_id,
                entity_id=item_id,
                old_values={"display_name": existing_item.display_name},
                ip_address=ip_address,
            )
    async def get_current_medications(
        self, patient_id: uuid.UUID, as_of: Optional[date] = None
    ) -> CurrentMedicationListResponse:
        """Read the authenticated patient's approved, date-active medication items."""
        effective_date = as_of or date.today()
        items = await self._rx_repo.list_current_medications(patient_id, effective_date)
        return CurrentMedicationListResponse(
            as_of=effective_date,
            medications=[PrescriptionItemDetailResponse.model_validate(item) for item in items],
        )
