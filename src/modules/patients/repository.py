import logging
import uuid
from datetime import date
from typing import List, Optional, Tuple

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.auth.models import User
from src.modules.patients.models import PatientProfile

logger = logging.getLogger(__name__)


class PatientRepository:
    """Repository handling PatientProfile database operations."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def create_patient_profile(
        self,
        user_id: uuid.UUID,
        name: str,
        primary_doctor_id: Optional[uuid.UUID] = None,
        dob: Optional[date] = None,
        sex: Optional[str] = None,
        timezone: str = "Asia/Ho_Chi_Minh",
        emergency_note: Optional[str] = None,
    ) -> PatientProfile:
        """Persist a new patient profile record."""
        profile = PatientProfile(
            user_id=user_id,
            primary_doctor_id=primary_doctor_id,
            name=name,
            dob=dob,
            sex=sex,
            timezone=timezone,
            emergency_note=emergency_note,
        )
        self._db.add(profile)
        await self._db.flush()
        return profile

    async def get_patient_with_user(
        self, user_id: uuid.UUID, for_update: bool = False
    ) -> Optional[Tuple[PatientProfile, User]]:
        """Fetch patient profile joined with user record in one query."""
        stmt = (
            select(PatientProfile, User)
            .join(User, PatientProfile.user_id == User.id)
            .where(PatientProfile.user_id == user_id)
        )
        if for_update:
            stmt = stmt.with_for_update()
        result = await self._db.execute(stmt)
        row = result.first()
        if row is None:
            return None
        return row[0], row[1]

    async def list_patients_for_doctor(
        self,
        doctor_id: Optional[uuid.UUID],
        page: int = 1,
        size: int = 10,
        search: Optional[str] = None,
    ) -> Tuple[List[Tuple[PatientProfile, User]], int]:
        """Fetch paginated patient profiles joined with users in a single query.

        doctor_id=None means unscoped (ADMIN). Otherwise scoped to that doctor's
        roster via primary_doctor_id — the WHERE clause is the RBAC boundary,
        never a post-fetch filter.
        """
        total_count_col = func.count().over().label("total_count")
        base_stmt = select(PatientProfile, User, total_count_col).join(
            User, PatientProfile.user_id == User.id
        )

        filters = []
        if doctor_id is not None:
            filters.append(PatientProfile.primary_doctor_id == doctor_id)
        if search and search.strip():
            term = f"%{search.strip()}%"
            filters.append(
                or_(
                    PatientProfile.name.ilike(term),
                    User.phone.ilike(term),
                )
            )

        if filters:
            base_stmt = base_stmt.where(*filters)

        offset = (page - 1) * size
        stmt = (
            base_stmt.order_by(PatientProfile.created_at.desc())
            .offset(offset)
            .limit(size)
        )
        result = await self._db.execute(stmt)
        rows = result.all()

        if not rows:
            if page == 1:
                return [], 0
            count_stmt = select(func.count(PatientProfile.user_id)).join(
                User, PatientProfile.user_id == User.id
            )
            if filters:
                count_stmt = count_stmt.where(*filters)
            total_count = (await self._db.execute(count_stmt)).scalar_one()
            return [], total_count

        total_count = rows[0].total_count if rows else 0
        items = [(row[0], row[1]) for row in rows]
        return items, total_count
