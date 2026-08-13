import logging
import uuid
from typing import Any, List, Optional, Tuple

from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.admin.models import AuditLog, DoctorProfile
from src.modules.auth.models import User

logger = logging.getLogger(__name__)


class DoctorRepository:
    """Repository handling DoctorProfile database operations."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def create_doctor_profile(
        self,
        user_id: uuid.UUID,
        name: str,
        license_no: str,
        specialty: Optional[str] = None,
    ) -> DoctorProfile:
        """Persist a new doctor profile record."""
        profile = DoctorProfile(
            user_id=user_id,
            name=name,
            license_no=license_no,
            specialty=specialty,
        )
        self._db.add(profile)
        await self._db.flush()
        return profile

    async def get_doctor_with_user(
        self, user_id: uuid.UUID, for_update: bool = False
    ) -> Optional[Tuple[DoctorProfile, User]]:
        """Fetch doctor profile joined with user record O(1)."""
        stmt = (
            select(DoctorProfile, User)
            .join(User, DoctorProfile.user_id == User.id)
            .where(DoctorProfile.user_id == user_id)
        )
        if for_update:
            stmt = stmt.with_for_update()
        result = await self._db.execute(stmt)
        row = result.first()
        if row is None:
            return None
        return row[0], row[1]

    async def get_doctor_by_license_no(
        self, license_no: str
    ) -> Optional[DoctorProfile]:
        """Fetch doctor profile by license number."""
        stmt = select(DoctorProfile).where(DoctorProfile.license_no == license_no)
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_doctors(
        self, page: int = 1, size: int = 10, search: Optional[str] = None
    ) -> Tuple[List[Tuple[DoctorProfile, User]], int]:
        """Fetch paginated doctor profiles joined with users.

        Count is a separate query rather than count().over() — the window
        function forces the planner to materialize the full filtered result
        before LIMIT can apply, which is a full scan on every page request.
        """
        filter_clause = None
        if search and search.strip():
            term = f"%{search.strip()}%"
            filter_clause = or_(
                DoctorProfile.name.ilike(term),
                User.phone.ilike(term),
                DoctorProfile.license_no.ilike(term),
            )

        count_stmt = select(func.count(DoctorProfile.user_id)).join(
            User, DoctorProfile.user_id == User.id
        )
        if filter_clause is not None:
            count_stmt = count_stmt.where(filter_clause)
        total_count = (await self._db.execute(count_stmt)).scalar_one()

        if total_count == 0:
            return [], 0

        base_stmt = select(DoctorProfile, User).join(
            User, DoctorProfile.user_id == User.id
        )
        if filter_clause is not None:
            base_stmt = base_stmt.where(filter_clause)

        offset = (page - 1) * size
        stmt = (
            base_stmt.order_by(DoctorProfile.created_at.desc())
            .offset(offset)
            .limit(size)
        )
        result = await self._db.execute(stmt)
        items = [(row[0], row[1]) for row in result.all()]
        return items, total_count

    async def update_doctor_profile(
        self,
        user_id: uuid.UUID,
        name: Optional[str] = None,
        specialty: Optional[str] = None,
    ) -> None:
        """Update doctor profile fields."""
        values: dict[str, Any] = {}
        if name is not None:
            values["name"] = name
        if specialty is not None:
            values["specialty"] = specialty

        if values:
            stmt = (
                update(DoctorProfile)
                .where(DoctorProfile.user_id == user_id)
                .values(**values)
            )
            await self._db.execute(stmt)


class AuditLogRepository:
    """Repository handling AuditLog database operations."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def create_audit_log(
        self,
        action: str,
        entity_type: str,
        actor_user_id: Optional[uuid.UUID] = None,
        entity_id: Optional[uuid.UUID] = None,
        old_values: Optional[dict[str, Any]] = None,
        new_values: Optional[dict[str, Any]] = None,
        changed_fields: Optional[List[str]] = None,
        ip_address: Optional[str] = None,
        device_info: Optional[str] = None,
    ) -> AuditLog:
        """Persist a new audit log record."""
        log = AuditLog(
            id=uuid.uuid4(),
            actor_user_id=actor_user_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            old_values=old_values,
            new_values=new_values,
            changed_fields=changed_fields,
            ip_address=ip_address,
            device_info=device_info,
        )
        self._db.add(log)
        await self._db.flush()
        return log

    async def list_audit_logs(
        self,
        page: int = 1,
        size: int = 10,
        actor_id: Optional[uuid.UUID] = None,
        entity_type: Optional[str] = None,
    ) -> Tuple[List[AuditLog], int]:
        """Fetch paginated audit logs with optional filters.

        Count is a separate query rather than count().over() — the window
        function forces the planner to materialize the full filtered result
        before LIMIT can apply, which is a full scan on every page request.
        """
        filters = []
        if actor_id is not None:
            filters.append(AuditLog.actor_user_id == actor_id)
        if entity_type is not None and entity_type.strip():
            filters.append(AuditLog.entity_type == entity_type.strip())

        count_stmt = select(func.count(AuditLog.id))
        if filters:
            count_stmt = count_stmt.where(*filters)
        total_count = (await self._db.execute(count_stmt)).scalar_one()

        if total_count == 0:
            return [], 0

        base_stmt = select(AuditLog)
        if filters:
            base_stmt = base_stmt.where(*filters)

        offset = (page - 1) * size
        stmt = (
            base_stmt.order_by(AuditLog.created_at.desc())
            .offset(offset)
            .limit(size)
        )
        result = await self._db.execute(stmt)
        items = [row[0] for row in result.all()]
        return items, total_count
