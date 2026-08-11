import logging
import math
import secrets
import string
import uuid
from typing import Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.common.exceptions import (
    ConflictException,
    NotFoundException,
    ValidationException,
)
from src.common.schemas import PageResponse
from src.core.security import hash_password, validate_phone_number
from src.modules.admin.repository import AuditLogRepository, DoctorRepository
from src.modules.admin.schemas import (
    AuditLogListResponse,
    CreateDoctorRequest,
    CreateDoctorResponse,
    DoctorDetailResponse,
    UpdateDoctorRequest,
)
from src.modules.auth.repository import AuthRepository
from src.modules.auth.schemas import MessageResponse

logger = logging.getLogger(__name__)


class AdminService:
    """Service handling Admin operations: Doctor CRUD and Audit Logs."""

    def __init__(
        self,
        db: AsyncSession,
        doctor_repository: DoctorRepository,
        audit_repository: AuditLogRepository,
        auth_repository: Optional[AuthRepository] = None,
    ) -> None:
        self._db = db
        self._doctor_repo = doctor_repository
        self._audit_repo = audit_repository
        self._auth_repo = auth_repository or AuthRepository(db)

    @staticmethod
    def _generate_temp_pin() -> str:
        """Generate a random 6-digit PIN string."""
        return "".join(secrets.choice(string.digits) for _ in range(6))

    async def create_doctor(
        self,
        request: CreateDoctorRequest,
        actor_payload: dict,
        ip_address: Optional[str] = None,
    ) -> CreateDoctorResponse:
        """Create a new Doctor account and profile.

        1. Clean and validate phone format.
        2. Check for duplicate phone in users table.
        3. Check for duplicate license_no in doctor_profiles table.
        4. Generate random 6-digit PIN and bcrypt hash it.
        5. Persist User, DoctorProfile, and AuditLog in one transaction.
        6. Return CreateDoctorResponse containing temp_password.
        """
        cleaned_phone = validate_phone_number(request.phone)

        temp_pin = self._generate_temp_pin()
        hashed_pin = hash_password(temp_pin)
        actor_user_id = (
            uuid.UUID(actor_payload["sub"]) if actor_payload.get("sub") else None
        )

        try:
            async with self._db.begin():
                existing_user = await self._auth_repo.get_user_by_phone(cleaned_phone)
                if existing_user is not None:
                    raise ConflictException(message="Phone number already registered")

                existing_doctor = await self._doctor_repo.get_doctor_by_license_no(
                    request.license_no
                )
                if existing_doctor is not None:
                    raise ConflictException(message="License number already registered")

                user = await self._auth_repo.create_user(
                    phone=cleaned_phone,
                    hashed_password=hashed_pin,
                    role="DOCTOR",
                )
                profile = await self._doctor_repo.create_doctor_profile(
                    user_id=user.id,
                    name=request.name,
                    license_no=request.license_no,
                    specialty=request.specialty,
                )
                await self._audit_repo.create_audit_log(
                    action="CREATE_DOCTOR",
                    entity_type="DOCTOR_PROFILE",
                    actor_user_id=actor_user_id,
                    entity_id=user.id,
                    new_values={
                        "phone": cleaned_phone,
                        "name": request.name,
                        "license_no": request.license_no,
                        "specialty": request.specialty,
                    },
                    ip_address=ip_address,
                )
        except IntegrityError as exc:
            logger.warning(f"IntegrityError creating doctor: {exc}")
            err_msg = str(exc).lower()
            if "license_no" in err_msg:
                raise ConflictException(message="License number already registered")
            elif "phone" in err_msg:
                raise ConflictException(message="Phone number already registered")
            else:
                raise ConflictException(
                    message="Phone or license number already registered"
                )

        doctor_detail = DoctorDetailResponse(
            user_id=user.id,
            phone=user.phone,
            role=user.role,
            status=user.status,
            name=profile.name,
            license_no=profile.license_no,
            specialty=profile.specialty,
            created_at=profile.created_at,
        )

        return CreateDoctorResponse(
            doctor=doctor_detail,
            temp_password=temp_pin,
        )

    async def list_doctors(
        self, page: int = 1, size: int = 10, search: Optional[str] = None
    ) -> PageResponse[DoctorDetailResponse]:
        """Fetch paginated doctor roster with search filter."""
        items, total_count = await self._doctor_repo.list_doctors(
            page=page, size=size, search=search
        )

        total_pages = math.ceil(total_count / size) if total_count > 0 else 0
        last = page >= total_pages if total_pages > 0 else True

        content = [
            DoctorDetailResponse(
                user_id=profile.user_id,
                phone=user.phone,
                role=user.role,
                status=user.status,
                name=profile.name,
                license_no=profile.license_no,
                specialty=profile.specialty,
                created_at=profile.created_at,
            )
            for profile, user in items
        ]

        return PageResponse(
            content=content,
            page_no=page,
            page_size=size,
            total_elements=total_count,
            total_pages=total_pages,
            last=last,
        )

    async def get_doctor(self, doctor_id: uuid.UUID) -> DoctorDetailResponse:
        """Fetch doctor detail by user ID."""
        result = await self._doctor_repo.get_doctor_with_user(doctor_id)
        if result is None:
            raise NotFoundException(message="Doctor not found")

        profile, user = result
        return DoctorDetailResponse(
            user_id=profile.user_id,
            phone=user.phone,
            role=user.role,
            status=user.status,
            name=profile.name,
            license_no=profile.license_no,
            specialty=profile.specialty,
            created_at=profile.created_at,
        )

    async def update_doctor(
        self,
        doctor_id: uuid.UUID,
        request: UpdateDoctorRequest,
        actor_payload: dict,
        ip_address: Optional[str] = None,
    ) -> DoctorDetailResponse:
        """Update doctor name, specialty, or account status."""
        if (
            request.name is None
            and request.specialty is None
            and request.status is None
        ):
            raise ValidationException(
                message="At least one field must be provided for update"
            )

        actor_user_id = (
            uuid.UUID(actor_payload["sub"]) if actor_payload.get("sub") else None
        )

        async with self._db.begin():
            existing = await self._doctor_repo.get_doctor_with_user(doctor_id)
            if existing is None:
                raise NotFoundException(message="Doctor not found")

            profile, user = existing

            old_values = {
                "name": profile.name,
                "specialty": profile.specialty,
                "status": user.status,
            }
            new_values = dict(old_values)
            changed_fields = []

            name_to_update = None
            specialty_to_update = None

            if request.name is not None and request.name != profile.name:
                new_values["name"] = request.name
                changed_fields.append("name")
                name_to_update = request.name
            if request.specialty is not None and request.specialty != profile.specialty:
                new_values["specialty"] = request.specialty
                changed_fields.append("specialty")
                specialty_to_update = request.specialty
            if request.status is not None and request.status != user.status:
                new_values["status"] = request.status
                changed_fields.append("status")

            if not changed_fields:
                return DoctorDetailResponse(
                    user_id=profile.user_id,
                    phone=user.phone,
                    role=user.role,
                    status=user.status,
                    name=profile.name,
                    license_no=profile.license_no,
                    specialty=profile.specialty,
                    created_at=profile.created_at,
                )

            if name_to_update is not None or specialty_to_update is not None:
                await self._doctor_repo.update_doctor_profile(
                    user_id=doctor_id,
                    name=name_to_update,
                    specialty=specialty_to_update,
                )
            if request.status is not None and request.status != user.status:
                await self._auth_repo.update_user_status(
                    user_id=doctor_id, status=request.status
                )
                if request.status == "INACTIVE":
                    await self._auth_repo.revoke_all_user_tokens(doctor_id)

            await self._audit_repo.create_audit_log(
                action="UPDATE_DOCTOR",
                entity_type="DOCTOR_PROFILE",
                actor_user_id=actor_user_id,
                entity_id=doctor_id,
                old_values=old_values,
                new_values=new_values,
                changed_fields=changed_fields,
                ip_address=ip_address,
            )

            await self._db.flush()
            await self._db.refresh(profile)
            await self._db.refresh(user)

        return DoctorDetailResponse(
            user_id=profile.user_id,
            phone=user.phone,
            role=user.role,
            status=user.status,
            name=profile.name,
            license_no=profile.license_no,
            specialty=profile.specialty,
            created_at=profile.created_at,
        )

    async def deactivate_doctor(
        self,
        doctor_id: uuid.UUID,
        actor_payload: dict,
        ip_address: Optional[str] = None,
    ) -> MessageResponse:
        """Deactivate a doctor account (soft delete)."""
        actor_user_id = (
            uuid.UUID(actor_payload["sub"]) if actor_payload.get("sub") else None
        )

        async with self._db.begin():
            existing = await self._doctor_repo.get_doctor_with_user(doctor_id)
            if existing is None:
                raise NotFoundException(message="Doctor not found")

            _, user = existing
            if user.status == "INACTIVE":
                raise ValidationException(message="Doctor is already inactive")

            await self._auth_repo.update_user_status(
                user_id=doctor_id, status="INACTIVE"
            )
            await self._auth_repo.revoke_all_user_tokens(doctor_id)
            await self._audit_repo.create_audit_log(
                action="DEACTIVATE_DOCTOR",
                entity_type="DOCTOR_PROFILE",
                actor_user_id=actor_user_id,
                entity_id=doctor_id,
                old_values={"status": user.status},
                new_values={"status": "INACTIVE"},
                changed_fields=["status"],
                ip_address=ip_address,
            )

        return MessageResponse(message="Doctor deactivated successfully")

    async def list_audit_logs(
        self,
        page: int = 1,
        size: int = 10,
        actor_id: Optional[uuid.UUID] = None,
        entity_type: Optional[str] = None,
    ) -> PageResponse[AuditLogListResponse]:
        """Fetch paginated audit logs with optional filters."""
        logs, total_count = await self._audit_repo.list_audit_logs(
            page=page, size=size, actor_id=actor_id, entity_type=entity_type
        )

        total_pages = math.ceil(total_count / size) if total_count > 0 else 0
        last = page >= total_pages if total_pages > 0 else True

        content = [
            AuditLogListResponse(
                id=log.id,
                actor_user_id=log.actor_user_id,
                action=log.action,
                entity_type=log.entity_type,
                entity_id=log.entity_id,
                old_values=log.old_values,
                new_values=log.new_values,
                ip_address=str(log.ip_address) if log.ip_address is not None else None,
                created_at=log.created_at,
            )
            for log in logs
        ]

        return PageResponse(
            content=content,
            page_no=page,
            page_size=size,
            total_elements=total_count,
            total_pages=total_pages,
            last=last,
        )
