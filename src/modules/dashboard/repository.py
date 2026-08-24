import uuid
from datetime import date, datetime
from typing import List, Optional, Tuple

from sqlalchemy import Exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from src.modules.adherence.models import Alert, HealthSurvey
from src.modules.agents.models import ScheduledDose
from src.modules.auth.models import User
from src.modules.patients.models import PatientProfile
from src.modules.prescriptions.models import Prescription


class DashboardRepository:
    """Read-only aggregate queries backing the doctor portal.

    Statement-only per CLAUDE.md: no commit/rollback, no business rules. Every
    method here reads across slices 3/5/6/7 tables; nothing in this module
    writes, so none of it needs a transaction block.
    """

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    @staticmethod
    def _has_prescribed_filter(
        doctor_id: uuid.UUID, patient_id_col: ColumnElement
    ) -> Exists:
        """Access predicate for a doctor reaching a patient's dashboard row.

        Mirrors PatientRepository._has_prescribed_filter rather than importing
        it — structure.md keeps modules self-contained, and the adherence
        router already duplicates a helper on the same reasoning. Same rule:
        a doctor's access is derived per request from the existence of a
        prescription they wrote for that patient, and evaporates with the last
        one.

        patient_id_col is supplied by the caller, not hardcoded: an EXISTS only
        auto-correlates against a table already in the enclosing FROM, and
        hardcoding it produced a cross-patient IDOR the last time it was
        assumed (see the note on the patients repository).
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
    def _open_alerts_count_subquery(patient_id_col: ColumnElement):
        """Correlated COUNT of alerts still awaiting a doctor.

        ACKNOWLEDGED counts as open: a doctor has seen it but the patient's
        situation is not closed, and hiding it would make the roster look
        calmer than it is. Only RESOLVED drops out.
        """
        return (
            select(func.count(Alert.id))
            .where(
                Alert.patient_id == patient_id_col,
                Alert.status.in_(("OPEN", "ACKNOWLEDGED")),
            )
            .correlate_except(Alert)
            .scalar_subquery()
        )

    @staticmethod
    def _last_survey_date_subquery(patient_id_col: ColumnElement):
        return (
            select(func.max(HealthSurvey.survey_date))
            .where(HealthSurvey.patient_id == patient_id_col)
            .correlate_except(HealthSurvey)
            .scalar_subquery()
        )

    @staticmethod
    def _dose_count_subquery(
        patient_id_col: ColumnElement,
        range_start: datetime,
        status: Optional[str] = None,
    ):
        """Correlated COUNT of doses scheduled since range_start.

        status=None counts every dose in the window (the denominator).
        """
        filters = [
            ScheduledDose.patient_id == patient_id_col,
            ScheduledDose.current_scheduled_at >= range_start,
        ]
        if status is not None:
            filters.append(ScheduledDose.status == status)
        return (
            select(func.count(ScheduledDose.id))
            .where(*filters)
            .correlate_except(ScheduledDose)
            .scalar_subquery()
        )

    async def list_dashboard_patients(
        self,
        range_start: datetime,
        doctor_id: Optional[uuid.UUID] = None,
        page: int = 1,
        size: int = 10,
        alert_status: Optional[str] = None,
        adherence_band: Optional[str] = None,
        search: Optional[str] = None,
    ) -> Tuple[List[Tuple[uuid.UUID, str, int, int, int, Optional[date]]], int]:
        """One page of roster rows: (patient_id, name, total_doses, taken_doses,
        open_alerts_count, last_survey_date).

        doctor_id=None means unscoped (ADMIN); otherwise restricted to patients
        this doctor has prescribed for.

        The per-row aggregates are correlated scalar subqueries rather than
        LEFT JOIN + GROUP BY: joining three one-to-many tables in a single
        query multiplies rows before grouping, and the counts come back wrong
        unless each is wrapped in its own DISTINCT. Subqueries stay correct by
        construction and run against the existing per-patient indexes, and at
        `size` <= 100 rows the cost is bounded.

        Count is a separate query rather than count().over() — the window
        function forces the planner to materialize the full filtered result
        before LIMIT can apply, which is a full scan on every page request.
        """
        filters = []
        total_doses = self._dose_count_subquery(PatientProfile.user_id, range_start)
        taken_doses = self._dose_count_subquery(
            PatientProfile.user_id, range_start, "TAKEN"
        )
        if doctor_id is not None:
            filters.append(self._has_prescribed_filter(doctor_id, PatientProfile.user_id))
        if search and search.strip():
            term = f"%{search.strip()}%"
            filters.append(or_(PatientProfile.name.ilike(term), User.phone.ilike(term)))
        if alert_status:
            filters.append(
                select(Alert.id)
                .where(
                    Alert.patient_id == PatientProfile.user_id,
                    Alert.status == alert_status,
                )
                .exists()
            )
        if adherence_band == "LOW":
            # No logged doses is displayed as 0% in the dashboard, so it belongs
            # in the low-adherence band too.
            filters.append(
                or_(
                    total_doses == 0,
                    taken_doses * 100 < total_doses * 50,
                )
            )
        elif adherence_band == "MEDIUM":
            filters.append(
                taken_doses * 100 >= total_doses * 50,
            )
            filters.append(taken_doses * 100 < total_doses * 70)
        elif adherence_band == "HIGH":
            filters.append(taken_doses * 100 >= total_doses * 70)

        count_stmt = select(func.count(PatientProfile.user_id)).join(
            User, PatientProfile.user_id == User.id
        )
        if filters:
            count_stmt = count_stmt.where(*filters)
        total_count = (await self._db.execute(count_stmt)).scalar_one()

        if total_count == 0:
            return [], 0

        open_alerts = self._open_alerts_count_subquery(PatientProfile.user_id)
        stmt = (
            select(
                PatientProfile.user_id,
                PatientProfile.name,
                total_doses,
                taken_doses,
                open_alerts,
                self._last_survey_date_subquery(PatientProfile.user_id),
            )
            .join(User, PatientProfile.user_id == User.id)
            .order_by(open_alerts.desc(), PatientProfile.created_at.desc())
            .offset((page - 1) * size)
            .limit(size)
        )
        if filters:
            stmt = stmt.where(*filters)

        result = await self._db.execute(stmt)
        rows = [
            (row[0], row[1], row[2], row[3], row[4], row[5]) for row in result.all()
        ]
        return rows, total_count

    async def get_patient_identity(
        self, patient_id: uuid.UUID, doctor_id: Optional[uuid.UUID] = None
    ) -> Optional[Tuple[uuid.UUID, str, str]]:
        """(user_id, name, phone) for one patient, or None when out of scope.

        Returning None for "exists but not yours" is deliberate — the caller
        turns both cases into the same 404 so the endpoint cannot be used to
        probe which patient UUIDs exist.
        """
        filters = [PatientProfile.user_id == patient_id]
        if doctor_id is not None:
            filters.append(self._has_prescribed_filter(doctor_id, PatientProfile.user_id))

        stmt = (
            select(PatientProfile.user_id, PatientProfile.name, User.phone)
            .join(User, PatientProfile.user_id == User.id)
            .where(*filters)
        )
        row = (await self._db.execute(stmt)).one_or_none()
        return (row[0], row[1], row[2]) if row is not None else None

    async def count_active_prescriptions(self, patient_id: uuid.UUID) -> int:
        """APPROVED prescriptions only — DRAFT is not yet in force and
        CANCELLED no longer is."""
        stmt = select(func.count(Prescription.id)).where(
            Prescription.patient_id == patient_id,
            Prescription.status == "APPROVED",
        )
        return (await self._db.execute(stmt)).scalar_one()

    async def get_dose_status_counts(
        self, patient_id: uuid.UUID, range_start: datetime
    ) -> Tuple[int, int, int, int]:
        """(total, taken, skipped, missed) doses scheduled since range_start,
        as one aggregate round trip using FILTER-based conditional counts."""
        stmt = select(
            func.count(ScheduledDose.id),
            func.count(ScheduledDose.id).filter(ScheduledDose.status == "TAKEN"),
            func.count(ScheduledDose.id).filter(ScheduledDose.status == "SKIPPED"),
            func.count(ScheduledDose.id).filter(ScheduledDose.status == "MISSED"),
        ).where(
            ScheduledDose.patient_id == patient_id,
            ScheduledDose.current_scheduled_at >= range_start,
        )
        row = (await self._db.execute(stmt)).one()
        return row[0], row[1], row[2], row[3]

    async def list_recent_alerts(self, patient_id: uuid.UUID, limit: int) -> List[Alert]:
        """Newest alerts for one patient regardless of status — the detail view
        shows recent history, not just what is still open. Rides
        idx_alerts_patient_created."""
        stmt = (
            select(Alert)
            .where(Alert.patient_id == patient_id)
            .order_by(Alert.created_at.desc())
            .limit(limit)
        )
        return list((await self._db.execute(stmt)).scalars().all())
