import logging
import math
import secrets
import string
import uuid
from typing import Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.common.exceptions import ConflictException, ForbiddenException, NotFoundException
from src.common.schemas import PageResponse
from src.core.security import hash_password, validate_phone_number
from src.modules.admin.repository import AuditLogRepository, DoctorRepository
from src.modules.auth.repository import AuthRepository
from src.modules.patients.repository import PatientRepository
from src.modules.patients.schemas import (
    CreatePatientByDoctorRequest,
    CreatePatientResponse,
    PatientDetailResponse,
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
    ) -> None:
        self._db = db
        self._patient_repo = patient_repository
        self._doctor_repo = doctor_repository
        self._audit_repo = audit_repository
        self._auth_repo = auth_repository or AuthRepository(db)

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
                    primary_doctor_id=doctor_id,
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
                        "primary_doctor_id": str(doctor_id),
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
        """Fetch paginated patient roster, scoped to the requesting doctor unless ADMIN."""
        role = actor_payload.get("role")
        doctor_id = None if role == "ADMIN" else uuid.UUID(actor_payload["sub"])

        items, total_count = await self._patient_repo.list_patients_for_doctor(
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
        """Fetch patient detail, scoped to the requesting doctor unless ADMIN.

        Out-of-scope access returns 404, never 403 — a 403 would confirm the
        patient ID exists under a different doctor, leaking PHI existence.
        """
        result = await self._patient_repo.get_patient_with_user(patient_id)
        if result is None:
            raise NotFoundException(message="Patient not found")

        profile, user = result
        role = actor_payload.get("role")
        if role != "ADMIN":
            requester_id = uuid.UUID(actor_payload["sub"])
            if profile.primary_doctor_id != requester_id:
                raise NotFoundException(message="Patient not found")

        return self._to_detail(profile, user)
