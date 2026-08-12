import logging
import uuid
from datetime import date
from typing import List, Optional, Tuple

from sqlalchemy import Exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.auth.models import User
from src.modules.patients.models import PatientProfile
from src.modules.prescriptions.models import Prescription

logger = logging.getLogger(__name__)


class PatientRepository:
    """Repository handling PatientProfile database operations."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    @staticmethod
    def _has_prescribed_filter(doctor_id: uuid.UUID) -> Exists:
        """Build the access predicate for a doctor reaching patient data.

        A doctor holds no ownership over any patient. The permission is derived
        per request from a single fact: at least one prescription written by
        this doctor exists for that patient. Nothing else grants access, and it
        disappears as soon as the last such prescription does.

        Correlated on PatientProfile.user_id so the same predicate composes into
        both the roster query and the single-patient fetch — keeping them from
        drifting apart, which is how detail fetch ended up unscoped.
        """
        return (
            select(Prescription.id)
            .where(
                Prescription.doctor_id == doctor_id,
                Prescription.patient_id == PatientProfile.user_id,
            )
            .exists()
        )

    async def create_patient_profile(
        self,
        user_id: uuid.UUID,
        name: str,
        dob: Optional[date] = None,
        sex: Optional[str] = None,
        timezone: str = "Asia/Ho_Chi_Minh",
        emergency_note: Optional[str] = None,
    ) -> PatientProfile:
        """Persist a new patient profile record."""
        profile = PatientProfile(
            user_id=user_id,
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
        self,
        user_id: uuid.UUID,
        requesting_doctor_id: Optional[uuid.UUID] = None,
        for_update: bool = False,
    ) -> Optional[Tuple[PatientProfile, User]]:
        """Fetch patient profile joined with user record in one query.

        requesting_doctor_id=None means unscoped (ADMIN). Otherwise the access
        predicate is folded into the same statement, so a patient the doctor has
        never prescribed for is indistinguishable from one that does not exist —
        both return None. That keeps the caller from leaking which patient UUIDs
        are real, and costs no extra round trip.
        """
        stmt = (
            select(PatientProfile, User)
            .join(User, PatientProfile.user_id == User.id)
            .where(PatientProfile.user_id == user_id)
        )
        if requesting_doctor_id is not None:
            stmt = stmt.where(self._has_prescribed_filter(requesting_doctor_id))
        if for_update:
            stmt = stmt.with_for_update()
        result = await self._db.execute(stmt)
        row = result.first()
        if row is None:
            return None
        return row[0], row[1]

    async def list_patients(
        self,
        doctor_id: Optional[uuid.UUID] = None,
        page: int = 1,
        size: int = 10,
        search: Optional[str] = None,
    ) -> Tuple[List[Tuple[PatientProfile, User]], int]:
        """Fetch paginated patient profiles joined with users.

        doctor_id=None means unscoped (ADMIN). Otherwise restricted to patients
        the doctor has written at least one prescription for.

        Count is a separate query rather than count().over() — the window
        function forces the planner to materialize the full filtered result
        before LIMIT can apply, which is a full scan on every page request.
        """
        filters = []
        if doctor_id is not None:
            filters.append(self._has_prescribed_filter(doctor_id))
        if search and search.strip():
            term = f"%{search.strip()}%"
            filters.append(
                or_(
                    PatientProfile.name.ilike(term),
                    User.phone.ilike(term),
                )
            )

        count_stmt = select(func.count(PatientProfile.user_id)).join(
            User, PatientProfile.user_id == User.id
        )
        if filters:
            count_stmt = count_stmt.where(*filters)
        total_count = (await self._db.execute(count_stmt)).scalar_one()

        if total_count == 0:
            return [], 0

        base_stmt = select(PatientProfile, User).join(
            User, PatientProfile.user_id == User.id
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
        items = [(row[0], row[1]) for row in result.all()]
        return items, total_count
