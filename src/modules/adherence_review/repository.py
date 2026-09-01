"""Indicator queries for the nightly graded-adherence review.

Central performance rule for this module: every method here returns numbers
for the ENTIRE population in one round trip. Never a query inside a
per-patient loop — that is exactly the N+1 this module exists to avoid (see
DashboardRepository's correlated-scalar-subquery pattern, which is correct at
page size <= 100 but would be quadratic across the whole patient table run
nightly).

Window definition: callers pass one explicit UTC `[start, end)` pair, derived
once from a single deployment-wide calendar day (see compute_window_bounds
below) rather than each patient's own local midnight — per-patient boundaries
would force one query per patient. Patients outside adherence_review_timezone
get a window skewed by their UTC offset; this is an accepted limitation
(docs/graded-adherence-implementation.md Stage 3.1), revisit only if the
platform ships outside one timezone.

All of a single nightly run's calls should share one REPEATABLE READ
transaction (the caller's responsibility, not this module's) so the
indicator packages describe one consistent instant — under READ COMMITTED a
patient actioning a dose mid-run could make the slot breakdown disagree with
the totals it is supposed to decompose.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from datetime import timezone as dt_timezone
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

from sqlalchemy import Exists, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from src.modules.adherence.models import HealthSurvey, SymptomReport
from src.modules.adherence_review.models import AdherenceReview
from src.modules.agents.models import ScheduledDose
from src.modules.auth.models import User
from src.modules.patients.models import PatientProfile
from src.modules.prescriptions.models import Prescription
from src.modules.prescriptions.models import PrescriptionItem


def compute_window_bounds(
    today_local: date, window_days: int, timezone_name: str
) -> tuple[datetime, datetime]:
    """[today_local - window_days, today_local) as a UTC datetime pair.

    A closed calendar window, not a rolling "now - N days": the escalation
    ladder compares night-over-night, so a night's window must be fixed at
    the moment it is computed rather than drifting as the batch runs long
    past midnight.
    """
    tz = ZoneInfo(timezone_name)
    end_local = datetime.combine(today_local, time.min, tzinfo=tz)
    start_local = end_local - timedelta(days=window_days)
    return start_local.astimezone(dt_timezone.utc), end_local.astimezone(dt_timezone.utc)


@dataclass(frozen=True)
class SeverityIndicators:
    """Query 1 — feeds Stage 4's deterministic severity rules only."""

    patient_id: uuid.UUID
    total: int
    taken: int
    skipped: int
    missed: int
    critical_missed: int


@dataclass(frozen=True)
class TrendIndicators:
    """Query 2 — prior window's totals, for a week-over-week delta."""

    total: int
    taken: int


@dataclass(frozen=True)
class SlotBreakdown:
    """Query 3 — one row per (patient, dose_slot). Feeds the LLM remedy
    classification only; never read by the severity rules."""

    dose_slot: str
    total: int
    missed: int


@dataclass(frozen=True)
class MedicationBreakdown:
    """Query 4 — one row per (patient, medication). Feeds the LLM remedy
    classification only; never read by the severity rules."""

    medication_id: uuid.UUID
    display_name: str
    total: int
    missed: int


@dataclass(frozen=True)
class SymptomEvidence:
    """Query 5 — cause evidence only (symptom_code/severity, a closed
    vocabulary). answers_json and free-text descriptions are deliberately
    excluded — see module docstring in the Stage 3 plan section 3.6."""

    survey_date: date
    symptom_code: str
    severity: str


@dataclass(frozen=True)
class PriorReview:
    """Query 6 — this patient's most recent review, for escalation."""

    review_date: date
    severity: str
    days_in_severity: int


@dataclass(frozen=True)
class PatientRosterEntry:
    """Query 7 (3.8) — display/delivery context for one patient."""

    name: str
    timezone: str
    status: str


def _is_due_filter(overdue_minutes: int):
    """Same rule as AdherenceLogRepository.get_dose_status_counts and
    DashboardRepository._is_due_filter: a dose still PENDING inside its
    grace window has had no chance to be actioned, so it belongs in neither
    numerator nor denominator. Overdue-but-PENDING counts as missed
    elsewhere so the reported figures sum to `total` and cannot race the
    15-minute missed-dose scan."""
    return or_(
        ScheduledDose.status != "PENDING",
        ScheduledDose.current_scheduled_at <= func.now() - timedelta(minutes=overdue_minutes),
    )


class AdherenceIndicatorRepository:
    """Statement-only, read-only. Every method scans the whole population in
    one query — see module docstring."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get_severity_indicators(
        self, range_start: datetime, range_end: datetime, overdue_minutes: int
    ) -> List[SeverityIndicators]:
        """One row per patient with at least one due dose in the window.
        A patient with zero scheduled doses (no prescriptions, or nothing
        due yet) produces no row at all — Stage 4's min-dose floor narrows
        this further for patients with a few doses but not enough to judge."""
        stmt = (
            select(
                ScheduledDose.patient_id,
                func.count(ScheduledDose.id).label("total"),
                func.count(ScheduledDose.id).filter(ScheduledDose.status == "TAKEN").label("taken"),
                func.count(ScheduledDose.id).filter(ScheduledDose.status == "SKIPPED").label("skipped"),
                func.count(ScheduledDose.id)
                .filter(ScheduledDose.status.in_(("MISSED", "PENDING")))
                .label("missed"),
                func.count(ScheduledDose.id)
                .filter(ScheduledDose.is_critical, ScheduledDose.status.in_(("MISSED", "PENDING")))
                .label("critical_missed"),
            )
            .where(
                ScheduledDose.current_scheduled_at >= range_start,
                ScheduledDose.current_scheduled_at < range_end,
                _is_due_filter(overdue_minutes),
            )
            .group_by(ScheduledDose.patient_id)
        )
        result = await self._db.execute(stmt)
        return [
            SeverityIndicators(
                patient_id=row.patient_id,
                total=row.total,
                taken=row.taken,
                skipped=row.skipped,
                missed=row.missed,
                critical_missed=row.critical_missed,
            )
            for row in result.all()
        ]

    async def get_trend_indicators(
        self, range_start: datetime, range_end: datetime, overdue_minutes: int
    ) -> Dict[uuid.UUID, TrendIndicators]:
        """Same shape as get_severity_indicators over the prior window
        (caller passes [D-2W, D-W)), total+taken only. One extra query for
        the whole population, not one per patient."""
        stmt = (
            select(
                ScheduledDose.patient_id,
                func.count(ScheduledDose.id).label("total"),
                func.count(ScheduledDose.id).filter(ScheduledDose.status == "TAKEN").label("taken"),
            )
            .where(
                ScheduledDose.current_scheduled_at >= range_start,
                ScheduledDose.current_scheduled_at < range_end,
                _is_due_filter(overdue_minutes),
            )
            .group_by(ScheduledDose.patient_id)
        )
        result = await self._db.execute(stmt)
        return {row.patient_id: TrendIndicators(total=row.total, taken=row.taken) for row in result.all()}

    async def get_slot_breakdown(
        self, range_start: datetime, range_end: datetime, overdue_minutes: int
    ) -> Dict[uuid.UUID, List[SlotBreakdown]]:
        """<=4 rows per patient (MORNING/NOON/EVENING/BEDTIME). Remedy-side
        only — never read by the severity rules in Stage 4."""
        stmt = (
            select(
                ScheduledDose.patient_id,
                ScheduledDose.dose_slot,
                func.count(ScheduledDose.id).label("total"),
                func.count(ScheduledDose.id)
                .filter(ScheduledDose.status.in_(("MISSED", "PENDING")))
                .label("missed"),
            )
            .where(
                ScheduledDose.current_scheduled_at >= range_start,
                ScheduledDose.current_scheduled_at < range_end,
                _is_due_filter(overdue_minutes),
                ScheduledDose.dose_slot.is_not(None),
            )
            .group_by(ScheduledDose.patient_id, ScheduledDose.dose_slot)
        )
        result = await self._db.execute(stmt)
        grouped: Dict[uuid.UUID, List[SlotBreakdown]] = {}
        for row in result.all():
            grouped.setdefault(row.patient_id, []).append(
                SlotBreakdown(dose_slot=row.dose_slot, total=row.total, missed=row.missed)
            )
        return grouped

    async def get_medication_breakdown(
        self,
        range_start: datetime,
        range_end: datetime,
        overdue_minutes: int,
        top_n: int = 5,
    ) -> Dict[uuid.UUID, List[MedicationBreakdown]]:
        """Grouped by (patient, medication_id), display_name read from
        PrescriptionItem (a real FK via prescription_item_id) rather than
        the medications catalog — medication_id itself carries no FK
        (dropped in migration 0007_drop_pi_med_fk) and the catalog row may
        have since been edited or deleted.

        Legacy rows with medication_id IS NULL (pre-migration-0011 schedule
        generation) are excluded rather than bucketed under a bogus "None"
        medication. Capped to the top `top_n` per patient by miss count in
        Python after fetch — a patient on 15 drugs should not produce a
        15-row LLM prompt."""
        stmt = (
            select(
                ScheduledDose.patient_id,
                ScheduledDose.medication_id,
                func.max(PrescriptionItem.display_name).label("display_name"),
                func.count(ScheduledDose.id).label("total"),
                func.count(ScheduledDose.id)
                .filter(ScheduledDose.status.in_(("MISSED", "PENDING")))
                .label("missed"),
            )
            .join(PrescriptionItem, ScheduledDose.prescription_item_id == PrescriptionItem.id)
            .where(
                ScheduledDose.current_scheduled_at >= range_start,
                ScheduledDose.current_scheduled_at < range_end,
                _is_due_filter(overdue_minutes),
                ScheduledDose.medication_id.is_not(None),
            )
            .group_by(ScheduledDose.patient_id, ScheduledDose.medication_id)
        )
        result = await self._db.execute(stmt)
        grouped: Dict[uuid.UUID, List[MedicationBreakdown]] = {}
        for row in result.all():
            grouped.setdefault(row.patient_id, []).append(
                MedicationBreakdown(
                    medication_id=row.medication_id,
                    display_name=row.display_name,
                    total=row.total,
                    missed=row.missed,
                )
            )
        for patient_id, rows in grouped.items():
            rows.sort(key=lambda r: r.missed, reverse=True)
            grouped[patient_id] = rows[:top_n]
        return grouped

    async def get_symptom_evidence(
        self, window_start: date, window_end: date
    ) -> Dict[uuid.UUID, List[SymptomEvidence]]:
        """Explicit join, not selectinload: HealthSurvey.symptom_reports is
        lazy="raise". Rides idx_health_surveys_date_id, no new index needed.
        Only symptom_code/severity selected — answers_json and free-text
        descriptions are patient-authored and excluded from the LLM payload
        entirely for v1 (see module docstring)."""
        stmt = (
            select(
                HealthSurvey.patient_id,
                HealthSurvey.survey_date,
                SymptomReport.symptom_code,
                SymptomReport.severity,
            )
            .join(SymptomReport, SymptomReport.survey_id == HealthSurvey.id)
            .where(
                HealthSurvey.survey_date >= window_start,
                HealthSurvey.survey_date <= window_end,
            )
        )
        result = await self._db.execute(stmt)
        grouped: Dict[uuid.UUID, List[SymptomEvidence]] = {}
        for row in result.all():
            grouped.setdefault(row.patient_id, []).append(
                SymptomEvidence(
                    survey_date=row.survey_date,
                    symptom_code=row.symptom_code,
                    severity=row.severity,
                )
            )
        return grouped

    async def get_prior_reviews(self, cutoff_date: date) -> Dict[uuid.UUID, PriorReview]:
        """Each patient's single most recent review at or after cutoff_date,
        via DISTINCT ON — one query for the whole population. Rides
        idx_adherence_reviews_patient_date_desc. A patient absent from the
        result has no review in the lookback window (never reviewed, or
        last reviewed too long ago to inform tonight's escalation step)."""
        stmt = (
            select(
                AdherenceReview.patient_id,
                AdherenceReview.review_date,
                AdherenceReview.severity,
                AdherenceReview.days_in_severity,
            )
            .distinct(AdherenceReview.patient_id)
            .where(AdherenceReview.review_date >= cutoff_date)
            .order_by(AdherenceReview.patient_id, AdherenceReview.review_date.desc())
        )
        result = await self._db.execute(stmt)
        return {
            row.patient_id: PriorReview(
                review_date=row.review_date,
                severity=row.severity,
                days_in_severity=row.days_in_severity,
            )
            for row in result.all()
        }

    async def get_patient_roster(
        self, patient_ids: List[uuid.UUID]
    ) -> Dict[uuid.UUID, PatientRosterEntry]:
        """Name/timezone/status for exactly the patients Query 1 already
        found to have due doses this window — not the whole patient_profiles
        table, and not one lookup per patient."""
        if not patient_ids:
            return {}
        stmt = (
            select(
                PatientProfile.user_id,
                PatientProfile.name,
                PatientProfile.timezone,
                User.status,
            )
            .join(User, PatientProfile.user_id == User.id)
            .where(PatientProfile.user_id.in_(patient_ids))
        )
        result = await self._db.execute(stmt)
        return {
            row.user_id: PatientRosterEntry(name=row.name, timezone=row.timezone, status=row.status)
            for row in result.all()
        }


def _access_filter(actor_id: uuid.UUID, patient_id_col: ColumnElement):
    """Role-agnostic access predicate, duplicated per structure.md's
    vertical-slice isolation rather than imported — mirrors
    AdherenceLogRepository._access_filter exactly: self-owned or
    doctor-prescribed are independent facts checked together."""

    def _has_prescribed_filter() -> Exists:
        return (
            select(Prescription.id)
            .where(Prescription.doctor_id == actor_id, Prescription.patient_id == patient_id_col)
            .exists()
        )

    return or_(
        patient_id_col == actor_id,
        _has_prescribed_filter(),
    )


class AdherenceReviewRepository:
    """Statement-only access to adherence_reviews rows: writes for the
    nightly orchestrator (Stage 6), access-scoped reads for the patient
    detail endpoint. Never commits/rolls back — the caller (service layer)
    owns the transaction."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def insert_review(self, fields: Dict[str, Any]) -> AdherenceReview:
        """Insert with alert_id/notification_delivery_id left unset (both
        nullable FKs, default NULL) -- the caller fills them in afterward via
        link_alert_and_notification, once the alert/notification rows this
        review references actually exist. Inserting the review FIRST, before
        either of those, is what makes uq_adherence_reviews_patient_date the
        real defence against a double-fired nightly run: a duplicate collides
        here and IntegrityError propagates before any alert or notification
        is ever created for the replay attempt."""
        review = AdherenceReview(**fields)
        self._db.add(review)
        await self._db.flush()
        return review

    async def link_alert_and_notification(
        self,
        review_id: uuid.UUID,
        alert_id: Optional[uuid.UUID],
        notification_delivery_id: Optional[uuid.UUID],
    ) -> None:
        """Second statement in the same transaction as insert_review, once
        the alert/notification it references have been created."""
        stmt = (
            update(AdherenceReview)
            .where(AdherenceReview.id == review_id)
            .values(alert_id=alert_id, notification_delivery_id=notification_delivery_id)
        )
        await self._db.execute(stmt)

    async def list_for_patient(
        self,
        patient_id: uuid.UUID,
        actor_id: uuid.UUID,
        page: int = 1,
        size: int = 10,
    ) -> Tuple[List[AdherenceReview], int]:
        """Newest first, access-scoped the same way as adherence logs and
        health surveys (self / doctor-prescribed / active-caregiver).
        Out-of-scope returns an empty page, matching
        HealthSurveyService.list_patient_surveys."""
        filters = [
            AdherenceReview.patient_id == patient_id,
            _access_filter(actor_id, AdherenceReview.patient_id),
        ]

        count_stmt = select(func.count(AdherenceReview.id)).where(*filters)
        total_count = (await self._db.execute(count_stmt)).scalar_one()

        if total_count == 0:
            return [], 0

        offset = (page - 1) * size
        stmt = (
            select(AdherenceReview)
            .where(*filters)
            .order_by(AdherenceReview.review_date.desc())
            .offset(offset)
            .limit(size)
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all()), total_count
