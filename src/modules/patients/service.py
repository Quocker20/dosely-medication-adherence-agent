import logging
import math
import secrets
import string
import uuid
from typing import List, Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.common.exceptions import ConflictException, ForbiddenException, NotFoundException
from src.common.schemas import PageResponse
from src.core.security import hash_password, validate_phone_number
from src.modules.admin.repository import AuditLogRepository, DoctorRepository
from src.modules.auth.repository import AuthRepository
from src.modules.patients.models import CaregiverLink, PatientRoutine
from src.modules.patients.repository import CaregiverRepository, PatientRepository
from src.modules.patients.schemas import (
    CaregiverLinkDetailResponse,
    CreateCaregiverLinkRequest,
    CreatePatientByDoctorRequest,
    CreatePatientResponse,
    PatientDetailResponse,
    PatientOnboardingRequest,
    PatientProfileDetailResponse,
    PatientRoutineResponse,
    UpdateRoutineRequest,
)

logger = logging.getLogger(__name__)


class PatientService:
    """Service handling Patient profile operations under Doctor/Admin scope."""

    def __init__(
        self,
        db: AsyncSession,
        patient_repository: PatientRepository,
        doctor_repository: DoctorRepository,
        audit_repository: AuditLogRepository,
        auth_repository: Optional[AuthRepository] = None,
        caregiver_repository: Optional[CaregiverRepository] = None,
    ) -> None:
        self._db = db
        self._patient_repo = patient_repository
        self._doctor_repo = doctor_repository
        self._audit_repo = audit_repository
        self._auth_repo = auth_repository or AuthRepository(db)
        self._caregiver_repo = caregiver_repository or CaregiverRepository(db)

    @staticmethod
    def _generate_temp_pin() -> str:
        """Generate a random 6-digit PIN string."""
        return "".join(secrets.choice(string.digits) for _ in range(6))

    @staticmethod
    def _to_detail(profile, user) -> PatientDetailResponse:
        return PatientDetailResponse(
            user_id=profile.user_id,
            phone=user.phone,
            role=user.role,
            status=user.status,
            name=profile.name,
            dob=profile.dob,
            sex=profile.sex,
            timezone=profile.timezone,
            privacy_consent_status=profile.privacy_consent_status,
            emergency_note=profile.emergency_note,
            created_at=profile.created_at,
            updated_at=profile.updated_at,
        )

    async def create_patient(
        self,
        request: CreatePatientByDoctorRequest,
        actor_payload: dict,
        ip_address: Optional[str] = None,
    ) -> CreatePatientResponse:
        """Doctor creates a new Patient account and profile.

        1. Clean and validate phone format.
        2. Confirm the acting doctor is still ACTIVE (token may outlive a
           deactivation — this closes most of that window, not all of it).
        3. Persist User, PatientProfile, and AuditLog in one transaction.
        4. Rely on DB unique constraint (phone) to reject duplicates via
           IntegrityError — no separate pre-check query (avoids TOCTOU race).
        """
        cleaned_phone = validate_phone_number(request.phone)
        doctor_id = uuid.UUID(actor_payload["sub"])

        temp_pin = self._generate_temp_pin()
        hashed_pin = hash_password(temp_pin)

        try:
            async with self._db.begin():
                doctor_row = await self._doctor_repo.get_doctor_with_user(doctor_id)
                if doctor_row is None:
                    raise NotFoundException(message="Doctor profile not found")
                _, doctor_user = doctor_row
                if doctor_user.status != "ACTIVE":
                    raise ForbiddenException(message="Doctor account is not active")

                user = await self._auth_repo.create_user(
                    phone=cleaned_phone,
                    hashed_password=hashed_pin,
                    role="PATIENT",
                )
                profile = await self._patient_repo.create_patient_profile(
                    user_id=user.id,
                    name=request.name,
                    dob=request.dob,
                    sex=request.sex,
                    timezone=request.timezone,
                    emergency_note=request.emergency_note,
                )
                await self._audit_repo.create_audit_log(
                    action="CREATE_PATIENT",
                    entity_type="PATIENT_PROFILE",
                    actor_user_id=doctor_id,
                    entity_id=user.id,
                    new_values={
                        "phone": cleaned_phone,
                        "name": request.name,
                    },
                    ip_address=ip_address,
                )
        except IntegrityError as exc:
            logger.warning(f"IntegrityError creating patient: {exc}")
            raise ConflictException(message="Phone number already registered")

        return CreatePatientResponse(
            patient=self._to_detail(profile, user),
            temp_password=temp_pin,
        )

    async def list_patients(
        self,
        actor_payload: dict,
        page: int = 1,
        size: int = 10,
        search: Optional[str] = None,
    ) -> PageResponse[PatientDetailResponse]:
        """Fetch paginated patient list, restricted to patients the requesting
        doctor has written at least one prescription for, unless ADMIN."""
        role = actor_payload.get("role")
        doctor_id = None if role == "ADMIN" else uuid.UUID(actor_payload["sub"])

        items, total_count = await self._patient_repo.list_patients(
            doctor_id=doctor_id, page=page, size=size, search=search
        )

        total_pages = math.ceil(total_count / size) if total_count > 0 else 0
        last = page >= total_pages if total_pages > 0 else True

        content = [self._to_detail(profile, user) for profile, user in items]

        return PageResponse(
            content=content,
            page_no=page,
            page_size=size,
            total_elements=total_count,
            total_pages=total_pages,
            last=last,
        )

    async def get_patient(
        self, patient_id: uuid.UUID, actor_payload: dict
    ) -> PatientDetailResponse:
        """Fetch patient detail, restricted to patients the requesting doctor has
        written at least one prescription for, unless ADMIN.

        Same derivation as list_patients — detail and roster must answer to one
        access rule. A patient outside that rule raises 404 rather than 403 so no
        doctor can probe which patient UUIDs exist.
        """
        role = actor_payload.get("role")
        doctor_id = None if role == "ADMIN" else uuid.UUID(actor_payload["sub"])

        result = await self._patient_repo.get_patient_with_user(
            patient_id, requesting_doctor_id=doctor_id
        )
        if result is None:
            raise NotFoundException(message="Patient not found")

        profile, user = result
        return self._to_detail(profile, user)

    @staticmethod
    def _to_routine_response(routine: PatientRoutine) -> PatientRoutineResponse:
        return PatientRoutineResponse(
            id=routine.id,
            patient_id=routine.patient_id,
            wake_time=routine.wake_time,
            breakfast_time=routine.breakfast_time,
            lunch_time=routine.lunch_time,
            dinner_time=routine.dinner_time,
            sleep_time=routine.sleep_time,
            updated_at=routine.updated_at,
        )

    @staticmethod
    def _to_caregiver_link_response(
        link: CaregiverLink, temp_password: Optional[str] = None
    ) -> CaregiverLinkDetailResponse:
        return CaregiverLinkDetailResponse(
            id=link.id,
            patient_id=link.patient_id,
            caregiver_user_id=link.caregiver_user_id,
            relationship=link.relationship_label,
            channels=list(link.channels or []),
            status=link.status,
            created_at=link.created_at,
            temp_password=temp_password,
        )

    async def onboard_patient(
        self, request: PatientOnboardingRequest, actor_payload: dict
    ) -> PatientProfileDetailResponse:
        """PATIENT self-onboarding: fills in profile details (row already exists
        from doctor-creation) and sets the initial daily routine.

        upsert_routine makes the routine half idempotent against a double-submit
        (e.g. a double-tapped submit button) without a pre-check race window.
        """
        patient_id = uuid.UUID(actor_payload["sub"])

        async with self._db.begin():
            await self._patient_repo.update_patient_profile(
                user_id=patient_id,
                name=request.name,
                dob=request.dob,
                sex=request.sex,
                timezone=request.timezone,
                emergency_note=request.emergency_note,
            )
            routine = await self._patient_repo.upsert_routine(
                patient_id=patient_id,
                wake_time=request.routine.wake_time,
                breakfast_time=request.routine.breakfast_time,
                lunch_time=request.routine.lunch_time,
                dinner_time=request.routine.dinner_time,
                sleep_time=request.routine.sleep_time,
            )

        result = await self._patient_repo.get_patient_with_user(patient_id)
        if result is None:
            raise NotFoundException(message="Patient not found")
        profile, user = result

        return PatientProfileDetailResponse(
            profile=self._to_detail(profile, user),
            routine=self._to_routine_response(routine),
        )

    async def get_routine(
        self, patient_id: uuid.UUID, actor_payload: dict
    ) -> PatientRoutineResponse:
        """Fetch a patient's routine. Access is role-agnostic: self-ownership,
        doctor-prescribed, and active-caregiver are independent facts checked
        together — the same user account can qualify through more than one
        (e.g. a PATIENT who is also someone else's caregiver). Out-of-scope
        -> 404, indistinguishable from a routine that does not exist.
        """
        actor_id = uuid.UUID(actor_payload["sub"])
        routine = await self._patient_repo.get_routine(patient_id, actor_id=actor_id)
        if routine is None:
            raise NotFoundException(message="Routine not found")
        return self._to_routine_response(routine)

    async def update_routine(
        self,
        patient_id: uuid.UUID,
        request: UpdateRoutineRequest,
        actor_payload: dict,
    ) -> PatientRoutineResponse:
        """Create or update a PATIENT's own daily routine.

        Doctor-created patient profiles do not initially have a routine row.
        The mobile onboarding flow intentionally collects routine data only,
        so PUT is an idempotent upsert instead of requiring the legacy
        /patients/me/profile endpoint to run first.
        """
        actor_id = uuid.UUID(actor_payload["sub"])
        if actor_id != patient_id:
            raise NotFoundException(message="Routine not found")

        async with self._db.begin():
            routine = await self._patient_repo.upsert_routine(
                patient_id=patient_id,
                wake_time=request.wake_time,
                breakfast_time=request.breakfast_time,
                lunch_time=request.lunch_time,
                dinner_time=request.dinner_time,
                sleep_time=request.sleep_time,
            )
        return self._to_routine_response(routine)

    async def _resolve_or_create_caregiver(self, cleaned_phone: str) -> tuple:
        """Find the caregiver's user account by phone, creating one with a temp
        PIN if it doesn't exist yet (same pattern as doctor-creates-patient).

        No dedicated CAREGIVER role: being a caregiver is entirely a fact of
        the caregiver_links row, not something recorded on users.role — so the
        same phone can equally already belong to a PATIENT or DOCTOR account
        (this lookup doesn't filter by role) and gain caregiver capacity on
        top of it. A brand-new phone with no prior identity is provisioned as
        role="PATIENT" (the most generic identity) with a placeholder
        patient_profiles row (name="NULL" literal text) in the same
        transaction, so it satisfies the onboarding PATIENT-role gate instead
        of 404/500-ing on a missing profile if it ever logs in directly.

        Runs as its own transaction, separate from the link insert: an
        IntegrityError here (concurrent create on the same new phone) would
        otherwise poison the outer transaction, since Postgres aborts the
        whole transaction block on any statement error. Catching it here and
        re-reading the now-existing row keeps this call race-safe without
        SAVEPOINTs.
        """
        user = await self._auth_repo.get_user_by_phone(cleaned_phone)
        if self._db.in_transaction():
            # commit(), not rollback(): ends the SELECT's autobegin transaction
            # the same way rollback() would (nothing was written either way),
            # but expire_on_commit=False on this sessionmaker means commit()
            # leaves `user`'s attributes populated. rollback() unconditionally
            # expires every object in the session regardless of that setting,
            # so a bare `user.id` access later (outside an awaited call, hence
            # outside the asyncio greenlet) raises MissingGreenlet trying to
            # lazily reload it — reproduced against a real DB while building
            # PrescriptionService's identical find-or-create-patient flow.
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
                    name="NULL",
                )
        except IntegrityError:
            user = await self._auth_repo.get_user_by_phone(cleaned_phone)
            if self._db.in_transaction():
                await self._db.commit()
            if user is None:
                raise
            return user, None
        return user, temp_pin

    async def create_caregiver_link(
        self,
        patient_id: uuid.UUID,
        request: CreateCaregiverLinkRequest,
        actor_payload: dict,
        ip_address: Optional[str] = None,
    ) -> CaregiverLinkDetailResponse:
        """PATIENT self-only (contract lists DOCTOR too, but caregiver
        management is explicitly kept out of doctor scope for this platform —
        deviation is intentional).

        1. Resolve-or-create the caregiver account by phone (own transaction).
        2. Insert the link; uq_caregiver_links_patient_caregiver rejects a
           duplicate atomically via IntegrityError -> 409, no pre-check SELECT.
        """
        actor_id = uuid.UUID(actor_payload["sub"])
        if actor_id != patient_id:
            raise ForbiddenException(message="Cannot manage caregivers for another patient")

        cleaned_phone = validate_phone_number(request.caregiver_phone)
        caregiver_user, temp_pin = await self._resolve_or_create_caregiver(cleaned_phone)

        try:
            async with self._db.begin():
                link = await self._caregiver_repo.create_link(
                    patient_id=patient_id,
                    caregiver_user_id=caregiver_user.id,
                    relationship=request.relationship,
                    channels=request.channels,
                )
                await self._audit_repo.create_audit_log(
                    action="ADD_CAREGIVER_LINK",
                    entity_type="CAREGIVER_LINK",
                    actor_user_id=patient_id,
                    entity_id=link.id,
                    new_values={
                        "caregiver_user_id": str(caregiver_user.id),
                        "relationship": request.relationship,
                    },
                    ip_address=ip_address,
                )
        except IntegrityError as exc:
            logger.warning(f"IntegrityError creating caregiver link: {exc}")
            raise ConflictException(message="Caregiver is already linked to this patient")

        return self._to_caregiver_link_response(link, temp_password=temp_pin)

    async def list_caregiver_links(
        self, patient_id: uuid.UUID, actor_payload: dict
    ) -> List[CaregiverLinkDetailResponse]:
        """PATIENT (self) or ADMIN only — DOCTOR excluded, same as create."""
        role = actor_payload.get("role")
        if role == "PATIENT":
            actor_id = uuid.UUID(actor_payload["sub"])
            if actor_id != patient_id:
                raise ForbiddenException(message="Cannot view another patient's caregivers")

        links = await self._caregiver_repo.list_by_patient(patient_id)
        return [self._to_caregiver_link_response(link) for link in links]

    async def delete_caregiver_link(
        self,
        patient_id: uuid.UUID,
        caregiver_link_id: uuid.UUID,
        actor_payload: dict,
        ip_address: Optional[str] = None,
    ) -> None:
        """PATIENT (self) or ADMIN only. Hard delete. patient_id ownership is
        re-verified via get_link before delete, blocking an IDOR where
        caregiver_link_id belongs to a different patient."""
        role = actor_payload.get("role")
        if role == "PATIENT":
            actor_id = uuid.UUID(actor_payload["sub"])
            if actor_id != patient_id:
                raise ForbiddenException(message="Cannot manage another patient's caregivers")

        async with self._db.begin():
            link = await self._caregiver_repo.get_link(caregiver_link_id, patient_id)
            if link is None:
                raise NotFoundException(message="Caregiver link not found")
            await self._caregiver_repo.delete_link(caregiver_link_id)
            await self._audit_repo.create_audit_log(
                action="REMOVE_CAREGIVER_LINK",
                entity_type="CAREGIVER_LINK",
                actor_user_id=uuid.UUID(actor_payload["sub"]),
                entity_id=caregiver_link_id,
                old_values={"caregiver_user_id": str(link.caregiver_user_id)},
                ip_address=ip_address,
            )
