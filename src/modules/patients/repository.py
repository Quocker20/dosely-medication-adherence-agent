import logging
import uuid
from datetime import date, time
from typing import List, Optional, Tuple

from sqlalchemy import Exists, delete, func, or_, select, update
from sqlalchemy.sql.elements import ColumnElement
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.auth.models import User
from src.modules.patients.models import CaregiverLink, PatientProfile, PatientRoutine
from src.modules.prescriptions.models import Prescription

logger = logging.getLogger(__name__)


class PatientRepository:
    """Repository handling PatientProfile database operations."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    @staticmethod
    def _has_prescribed_filter(
        doctor_id: uuid.UUID, patient_id_col: ColumnElement
    ) -> Exists:
        """Build the access predicate for a doctor reaching patient data.

        A doctor holds no ownership over any patient. The permission is derived
        per request from a single fact: at least one prescription written by
        this doctor exists for that patient. Nothing else grants access, and it
        disappears as soon as the last such prescription does.

        patient_id_col is the column to correlate against, supplied by the
        caller rather than hardcoded to PatientProfile.user_id. An EXISTS only
        auto-correlates to a table already present in the enclosing query's
        FROM — hardcoding it here worked for list_patients/get_patient_with_user
        (both select PatientProfile) but silently produced an UNCORRELATED
        subquery when reused from get_routine (selects PatientRoutine, never
        joins PatientProfile), which made the doctor-scope check pass for any
        doctor with any prescription for any patient — a cross-patient IDOR.
        """
        return (
            select(Prescription.id)
            .where(
                Prescription.doctor_id == doctor_id,
                Prescription.patient_id == patient_id_col,
            )
            .exists()
        )

    @staticmethod
    def _has_active_caregiver_filter(caregiver_user_id: uuid.UUID) -> Exists:
        """Build the access predicate for a caregiver reaching a patient's routine.

        Mirrors _has_prescribed_filter: access is derived per request from a
        single fact — an ACTIVE caregiver_links row for (patient, caregiver) —
        not stored on the patient. Correlated on PatientRoutine.patient_id so it
        composes directly into the routine SELECT with no extra round trip.
        Rides uq_caregiver_links_patient_caregiver (patient_id, caregiver_user_id)
        as an index-only probe.
        """
        return (
            select(CaregiverLink.id)
            .where(
                CaregiverLink.caregiver_user_id == caregiver_user_id,
                CaregiverLink.patient_id == PatientRoutine.patient_id,
                CaregiverLink.status == "ACTIVE",
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
            stmt = stmt.where(
                self._has_prescribed_filter(requesting_doctor_id, PatientProfile.user_id)
            )
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
            filters.append(self._has_prescribed_filter(doctor_id, PatientProfile.user_id))
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

    async def update_patient_profile(
        self,
        user_id: uuid.UUID,
        name: str,
        dob: Optional[date] = None,
        sex: Optional[str] = None,
        timezone: str = "Asia/Ho_Chi_Minh",
        emergency_note: Optional[str] = None,
    ) -> None:
        """Update self-onboarding profile fields for an existing patient row.

        Single UPDATE by primary key (user_id) — no prior SELECT needed, the
        caller already knows the row exists (it's the authenticated patient).
        """
        stmt = (
            update(PatientProfile)
            .where(PatientProfile.user_id == user_id)
            .values(
                name=name,
                dob=dob,
                sex=sex,
                timezone=timezone,
                emergency_note=emergency_note,
            )
        )
        await self._db.execute(stmt)

    async def get_routine(
        self, patient_id: uuid.UUID, actor_id: uuid.UUID
    ) -> Optional[PatientRoutine]:
        """Fetch a patient's routine, single row by unique patient_id.

        Access is role-agnostic: a single user can simultaneously be the
        patient themselves, a doctor who has prescribed for them, and/or an
        active caregiver for them — nothing on the users.role column
        determines which; each is an independent fact checked in the same
        query. Out-of-scope caller and non-existent routine both return None.
        """
        stmt = select(PatientRoutine).where(
            PatientRoutine.patient_id == patient_id,
            or_(
                PatientRoutine.patient_id == actor_id,
                self._has_prescribed_filter(actor_id, PatientRoutine.patient_id),
                self._has_active_caregiver_filter(actor_id),
            ),
        )
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    _ROUTINE_FIELDS = (
        "wake_time",
        "breakfast_time",
        "lunch_time",
        "dinner_time",
        "sleep_time",
    )

    async def upsert_routine(
        self,
        patient_id: uuid.UUID,
        updates: dict[str, Optional[time]],
    ) -> PatientRoutine:
        """Insert-or-update only the routine fields the caller actually sent.

        INSERT ... ON CONFLICT (patient_id) DO UPDATE is race-safe against a
        concurrent double-submit of the onboarding endpoint — no SELECT-then-
        branch window where two requests could both see "no row yet".

        `updates` carries only the fields present in the request (the caller
        builds it with exclude_unset). DO UPDATE sets exactly those columns, so
        a partial PUT no longer NULLs the anchors it didn't mention: wiping
        breakfast_time is what makes expand_schedule raise
        MissingRoutineAnchorError, which would silently cost the patient every
        morning reminder. The trade-off is that a field can no longer be
        cleared back to NULL through this path — deliberate, since every
        patient is seeded with a full default routine at creation.
        """
        unknown = set(updates) - set(self._ROUTINE_FIELDS)
        if unknown:
            raise ValueError(f"Unknown routine field(s): {sorted(unknown)}")

        if not updates:
            # Nothing to write. Return the current row rather than clobbering
            # it with an all-NULL insert.
            existing = await self._db.execute(
                select(PatientRoutine).where(PatientRoutine.patient_id == patient_id)
            )
            routine = existing.scalar_one_or_none()
            if routine is not None:
                return routine
            updates = {}

        stmt = pg_insert(PatientRoutine).values(patient_id=patient_id, **updates)
        stmt = stmt.on_conflict_do_update(
            index_elements=[PatientRoutine.patient_id],
            set_={field: stmt.excluded[field] for field in updates}
            or {"patient_id": stmt.excluded.patient_id},
        ).returning(PatientRoutine)
        result = await self._db.execute(stmt)
        return result.scalar_one()

    async def update_routine(
        self,
        patient_id: uuid.UUID,
        wake_time: Optional[time] = None,
        breakfast_time: Optional[time] = None,
        lunch_time: Optional[time] = None,
        dinner_time: Optional[time] = None,
        sleep_time: Optional[time] = None,
    ) -> Optional[PatientRoutine]:
        """Update an existing routine row. Returns None if no row exists yet
        (caller treats that as "complete onboarding first" -> 404)."""
        stmt = (
            update(PatientRoutine)
            .where(PatientRoutine.patient_id == patient_id)
            .values(
                wake_time=wake_time,
                breakfast_time=breakfast_time,
                lunch_time=lunch_time,
                dinner_time=dinner_time,
                sleep_time=sleep_time,
            )
            .returning(PatientRoutine)
        )
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()


class CaregiverRepository:
    """Repository handling CaregiverLink database operations."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def create_link(
        self,
        patient_id: uuid.UUID,
        caregiver_user_id: uuid.UUID,
        relationship: Optional[str],
        channels: List[str],
    ) -> CaregiverLink:
        """Persist a new caregiver link. Relies on
        uq_caregiver_links_patient_caregiver to reject duplicates via
        IntegrityError — no pre-check SELECT (avoids TOCTOU race)."""
        link = CaregiverLink(
            patient_id=patient_id,
            caregiver_user_id=caregiver_user_id,
            relationship_label=relationship,
            channels=channels,
        )
        self._db.add(link)
        await self._db.flush()
        return link

    async def list_by_patient(self, patient_id: uuid.UUID) -> List[CaregiverLink]:
        """Fetch all caregiver links for a patient.

        Single SELECT, no join — the response only needs caregiver_user_id
        (UUID), not the caregiver's user row, so there is no N+1 risk here.
        Rides uq_caregiver_links_patient_caregiver (patient_id leading column).
        """
        stmt = select(CaregiverLink).where(CaregiverLink.patient_id == patient_id)
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def get_link(
        self, link_id: uuid.UUID, patient_id: uuid.UUID
    ) -> Optional[CaregiverLink]:
        """Fetch a single link scoped to its owning patient — the patient_id
        check blocks an IDOR where a valid link_id from a different patient is
        passed in the path."""
        stmt = select(CaregiverLink).where(
            CaregiverLink.id == link_id, CaregiverLink.patient_id == patient_id
        )
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def delete_link(self, link_id: uuid.UUID) -> None:
        """Hard-delete a caregiver link by ID."""
        stmt = delete(CaregiverLink).where(CaregiverLink.id == link_id)
        await self._db.execute(stmt)
