"""Deterministic dose-schedule expansion — planning is code, not an LLM call
(src/core/config.py: "luật lâm sàng chạy bằng code xác định"). Pure functions:
no DB, no I/O, no wall-clock reads — `today` is always passed in, so this is
unit-testable without mocking anything.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import cast
from zoneinfo import ZoneInfo

# (dose column, routine anchor key, fixed offset minutes | None = derive from meal_relation)
_DOSE_SLOTS: tuple[tuple[str, str, int | None], ...] = (
    ("morning_dose", "breakfast", None),
    ("noon_dose", "lunch", None),
    ("evening_dose", "dinner", None),
    ("bedtime_dose", "sleep", -30),
)

_DOSE_SLOT_NAMES: dict[str, str] = {
    "morning_dose": "MORNING",
    "noon_dose": "NOON",
    "evening_dose": "EVENING",
    "bedtime_dose": "BEDTIME",
}

_MEAL_OFFSET_MINUTES: dict[str | None, int] = {
    "BEFORE_MEAL": -30,
    "AFTER_MEAL": 30,
    "WITH_MEAL": 0,
    None: 0,
}


def _normalize_meal_relation(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.upper()
    if normalized not in _MEAL_OFFSET_MINUTES:
        raise InvalidPrescriptionTimingError("Unsupported meal_relation in approved prescription item")
    return normalized


@dataclass(frozen=True)
class RoutineTimes:
    """Plain snapshot of a patient's routine, decoupled from the ORM model.

    Missing anchors stay missing: the planner must request review rather than
    inventing a meal or sleep time. ``wake`` is accepted for symmetry with the
    schema even though no dose slot anchors to it today.
    """

    wake: time | None = None
    breakfast: time | None = None
    lunch: time | None = None
    dinner: time | None = None
    sleep: time | None = None

    def anchor(self, key: str) -> time:
        value = getattr(self, key)
        if value is None:
            raise MissingRoutineAnchorError(f"Routine anchor '{key}' is required for an approved prescription slot")
        return value


# day -> {anchor_key: overridden_time}, anchor_key matching RoutineTimes field
# names exactly ("breakfast"/"lunch"/"dinner"/"sleep" — never "wake").
DayAnchorOverrides = dict[date, dict[str, time]]


@dataclass(frozen=True)
class PlannableItem:
    """Plain snapshot of the PrescriptionItem fields the planner needs."""

    id: uuid.UUID
    medication_id: uuid.UUID | None
    dose_unit: str
    morning_dose: Decimal | None
    noon_dose: Decimal | None
    evening_dose: Decimal | None
    bedtime_dose: Decimal | None
    meal_relation: str | None
    minimum_interval_minutes: int | None
    start_date: date
    end_date: date | None
    is_critical: bool = False
    # 1 = every day, 2 = every other day, etc. Doctor-set, never agent-writable.
    interval_days: int = 1


@dataclass(frozen=True)
class ScheduleRow:
    prescription_item_id: uuid.UUID
    medication_id: uuid.UUID | None
    dose_slot: str
    dose_value: Decimal
    dose_unit: str
    meal_relation: str | None
    original_scheduled_at: datetime
    current_scheduled_at: datetime
    status: str = "PENDING"
    snooze_count: int = 0
    notification_group_id: uuid.UUID | None = None
    # Pure carried value from PlannableItem.is_critical — must never
    # participate in slot selection, gap validation, or any scheduling
    # decision. See docs/graded-adherence-implementation.md Stage 2.
    is_critical: bool = False


@dataclass(frozen=True)
class RetainedDoseSnapshot:
    """Immutable projection of a schedule row locked during rescheduling."""

    prescription_item_id: uuid.UUID
    dose_slot: str | None
    original_scheduled_at: datetime
    current_scheduled_at: datetime
    status: str


class PlanningNeedsReviewError(ValueError):
    """A deterministic clinical constraint could not be satisfied safely.

    Callers must preserve the active schedule and expose NEEDS_REVIEW rather
    than guessing a replacement time or treating this as an infrastructure
    failure.
    """


class MissingRoutineAnchorError(PlanningNeedsReviewError):
    """An approved dose slot has no corresponding patient routine anchor."""


class ScheduleConstraintError(PlanningNeedsReviewError):
    """Approved timing constraints conflict with the candidate schedule."""


class InvalidPrescriptionTimingError(PlanningNeedsReviewError):
    """Approved timing/dose data cannot be interpreted without guessing."""


class FrequencyGuardrailError(PlanningNeedsReviewError):
    """Raised by validate_frequency_guardrails when a PlannableItem requests
    more doses/day than settings.max_frequency_per_day allows. A distinct
    type (not a bare ValueError) so SchedulingService.execute_run's
    error_code (type(exc).__name__) is meaningful on GET /agent-runs/{id}
    rather than a generic 'ValueError'."""


def validate_prescription_inputs(items: list[PlannableItem]) -> None:
    """Reject malformed approved inputs instead of silently dropping doses."""
    for item in items:
        doses = (
            item.morning_dose,
            item.noon_dose,
            item.evening_dose,
            item.bedtime_dose,
        )
        if all(dose is None for dose in doses):
            raise InvalidPrescriptionTimingError(f"PrescriptionItem {item.id} has no configured dose slots")
        if any(dose is not None and dose <= 0 for dose in doses):
            raise InvalidPrescriptionTimingError(f"PrescriptionItem {item.id} contains a non-positive dose")
        if item.minimum_interval_minutes is not None and item.minimum_interval_minutes <= 0:
            raise InvalidPrescriptionTimingError(f"PrescriptionItem {item.id} has a non-positive minimum interval")
        if item.interval_days < 1:
            raise InvalidPrescriptionTimingError(f"PrescriptionItem {item.id} has a non-positive interval_days")
        _normalize_meal_relation(item.meal_relation)


def validate_frequency_guardrails(items: list[PlannableItem], max_per_day: int) -> None:
    """Code-enforced guardrail (src/core/config.py: max_frequency_per_day) —
    not LLM-enforced. Counts non-null/non-zero dose columns per item, which
    is exactly the item's doses/day, and rejects the whole run if any item
    exceeds max_per_day. Called before expand_schedule so a violating item
    never reaches date-expansion at all.

    The "dose is not None and dose > 0" test deliberately mirrors
    _candidate_slots_for_day's own slot-inclusion check below, so "frequency"
    here means precisely what expand_schedule will actually schedule.
    """
    for item in items:
        frequency = sum(
            1
            for dose in (item.morning_dose, item.noon_dose, item.evening_dose, item.bedtime_dose)
            if dose is not None and dose > 0
        )
        if frequency > max_per_day:
            raise FrequencyGuardrailError(
                f"PrescriptionItem {item.id}: {frequency} doses/day requested, "
                f"exceeds max_frequency_per_day={max_per_day}"
            )


def _item_horizon(
    item: PlannableItem, today: date, horizon_days: int, max_treatment_days: int
) -> tuple[date, date] | None:
    """Effective [start, end] date range to generate for this item, or None
    if nothing falls in range today."""
    range_start = max(item.start_date, today)
    ceiling = min(
        item.end_date if item.end_date is not None else date.max,
        today + timedelta(days=horizon_days),
        item.start_date + timedelta(days=max_treatment_days),
    )
    if range_start > ceiling:
        return None
    return range_start, ceiling


def _first_dosing_day(range_start: date, item_start_date: date, interval_days: int) -> date:
    """First day on/after `range_start` that is a real dosing day for an item
    dosed every `interval_days` days from `item_start_date`.

    Deliberately phase-locked to item_start_date rather than starting the
    step from range_start itself: for an item already mid-treatment (e.g.
    start_date 9 days ago, interval_days=2, today somewhere in between),
    stepping from range_start would silently re-phase the whole rest of the
    regimen onto a different day-of-week than the one the doctor actually
    prescribed.
    """
    elapsed_days = (range_start - item_start_date).days
    remainder = elapsed_days % interval_days
    if remainder == 0:
        return range_start
    return range_start + timedelta(days=interval_days - remainder)


def _slot_local_dt(day: date, anchor: time, offset_minutes: int) -> datetime:
    """Combine day + anchor time + offset as a naive local datetime, letting
    timedelta arithmetic carry a cross-midnight offset (e.g. a sleep anchor
    resolved to 00:15 with a -30m bedtime offset lands at 23:45 the evening
    before) instead of wrapping time-of-day arithmetic by hand."""
    return datetime.combine(day, anchor) + timedelta(minutes=offset_minutes)


# A sleep time earlier than midday is read as "after midnight", i.e. it
# belongs to the *following* calendar day: someone who reports going to sleep
# at 01:00 on Monday means 01:00 Tuesday morning. Meal anchors never need
# this — 07:00 on Monday is unambiguously Monday morning. A fixed cutoff
# keeps this a deterministic rule rather than a guess about the patient.
_AFTER_MIDNIGHT_SLEEP_CUTOFF = time(12, 0)


def _anchor_day(anchor_key: str, anchor_time: time, day: date) -> date:
    """Calendar day the anchor instant for `day` actually falls on.

    Only ``sleep`` can roll over. Without this, a post-midnight sleep time is
    combined with `day` itself, putting the bedtime slot ~23 hours early — in
    the past for any same-day report, where expand_schedule's caller drops it
    and the dose silently disappears from the schedule.
    """
    if anchor_key == "sleep" and anchor_time < _AFTER_MIDNIGHT_SLEEP_CUTOFF:
        return day + timedelta(days=1)
    return day


def _candidate_slots_for_day(item: PlannableItem, routine: RoutineTimes, day: date) -> list[tuple[str, datetime]]:
    slots: list[tuple[str, datetime]] = []
    for dose_field, anchor_key, fixed_offset in _DOSE_SLOTS:
        dose_value = getattr(item, dose_field)
        if dose_value is None or dose_value <= 0:
            continue
        offset = (
            fixed_offset
            if fixed_offset is not None
            else _MEAL_OFFSET_MINUTES[_normalize_meal_relation(item.meal_relation)]
        )
        anchor_time = routine.anchor(anchor_key)
        local_dt = _slot_local_dt(_anchor_day(anchor_key, anchor_time, day), anchor_time, offset)
        slots.append((dose_field, local_dt))
    return slots


def _validate_min_gap(slots: list[tuple[str, datetime]], min_gap_minutes: int) -> list[tuple[str, datetime]]:
    """Return chronologically ordered slots or reject an unsafe candidate.

    Moving a meal-anchored slot to make the interval fit would silently break
    another approved constraint. The planner therefore never repairs this
    conflict by guessing a new time.
    """
    ordered_slots = sorted(slots, key=lambda slot: slot[1])
    for previous, current in zip(ordered_slots, ordered_slots[1:]):
        actual_gap = current[1] - previous[1]
        if actual_gap < timedelta(minutes=min_gap_minutes):
            raise ScheduleConstraintError(
                f"Dose slots {previous[0]} and {current[0]} are only "
                f"{int(actual_gap.total_seconds() // 60)} minutes apart; "
                f"minimum is {min_gap_minutes} minutes"
            )
    return ordered_slots


def _validate_cross_day_gaps(rows: list[ScheduleRow], minimums: dict[uuid.UUID, int]) -> None:
    """Validate consecutive doses for each item across the whole horizon."""
    by_item: dict[uuid.UUID, list[ScheduleRow]] = {}
    for row in rows:
        by_item.setdefault(row.prescription_item_id, []).append(row)

    for item_id, item_rows in by_item.items():
        ordered = sorted(item_rows, key=lambda row: row.current_scheduled_at)
        minimum = timedelta(minutes=minimums[item_id])
        for previous, current in zip(ordered, ordered[1:]):
            actual_gap = current.current_scheduled_at - previous.current_scheduled_at
            if actual_gap < minimum:
                raise ScheduleConstraintError(
                    f"PrescriptionItem {item_id}: consecutive doses are "
                    f"{int(actual_gap.total_seconds() // 60)} minutes apart; "
                    f"minimum is {minimums[item_id]} minutes"
                )


def validate_candidate_boundaries(
    items: list[PlannableItem],
    candidates: list[ScheduleRow],
    retained_times: dict[uuid.UUID, list[datetime]],
    default_min_gap_minutes: int,
) -> None:
    """Check regenerated candidates against retained dose rows.

    Rescheduling may replace only future PENDING rows. A TAKEN, SKIPPED,
    MISSED, sent/in-progress, or already-due row remains authoritative and
    must participate in the minimum-interval check.
    """
    minimums = {item.id: item.minimum_interval_minutes or default_min_gap_minutes for item in items}
    candidate_times: dict[uuid.UUID, list[datetime]] = {}
    for row in candidates:
        candidate_times.setdefault(row.prescription_item_id, []).append(row.current_scheduled_at)

    for item_id, new_times in candidate_times.items():
        timeline = [
            *((timestamp, "retained") for timestamp in retained_times.get(item_id, [])),
            *((timestamp, "candidate") for timestamp in new_times),
        ]
        timeline.sort(key=lambda entry: entry[0])
        minimum = timedelta(minutes=minimums[item_id])
        for previous, current in zip(timeline, timeline[1:]):
            if previous[1] == current[1] == "retained":
                continue
            actual_gap = current[0] - previous[0]
            if actual_gap < minimum:
                raise ScheduleConstraintError(
                    f"PrescriptionItem {item_id}: regenerated dose boundary is "
                    f"{int(actual_gap.total_seconds() // 60)} minutes; "
                    f"minimum is {minimums[item_id]} minutes"
                )


def reconcile_reschedule_candidates(
    items: list[PlannableItem],
    candidates: list[ScheduleRow],
    locked_schedule: list[RetainedDoseSnapshot],
    now: datetime,
    patient_timezone: str,
    default_min_gap_minutes: int,
) -> list[ScheduleRow]:
    """Preserve authoritative rows and return only safe replacement candidates."""
    retained = [dose for dose in locked_schedule if not (dose.status == "PENDING" and dose.current_scheduled_at > now)]
    timezone = ZoneInfo(patient_timezone)
    retained_keys: set[tuple[uuid.UUID, str, date]] = set()
    retained_times: dict[uuid.UUID, list[datetime]] = {}
    legacy_days: set[tuple[uuid.UUID, date]] = set()
    for dose in retained:
        local_day = dose.original_scheduled_at.astimezone(timezone).date()
        retained_times.setdefault(dose.prescription_item_id, []).append(dose.current_scheduled_at)
        if dose.dose_slot is None:
            legacy_days.add((dose.prescription_item_id, local_day))
        else:
            retained_keys.add((dose.prescription_item_id, dose.dose_slot, local_day))

    future_candidates = [row for row in candidates if row.current_scheduled_at > now]
    for row in future_candidates:
        local_day = row.current_scheduled_at.astimezone(timezone).date()
        if (row.prescription_item_id, local_day) in legacy_days:
            raise PlanningNeedsReviewError("Legacy retained dose lacks a slot snapshot")

    reconciled = [
        row
        for row in future_candidates
        if (
            row.prescription_item_id,
            row.dose_slot,
            row.current_scheduled_at.astimezone(timezone).date(),
        )
        not in retained_keys
    ]
    validate_candidate_boundaries(
        items,
        reconciled,
        retained_times,
        default_min_gap_minutes,
    )
    return reconciled


def expand_schedule(
    items: list[PlannableItem],
    routine: RoutineTimes,
    patient_timezone: str,
    today: date,
    horizon_days: int,
    default_min_gap_minutes: int,
    max_treatment_days: int,
    *,
    overrides: DayAnchorOverrides | None = None,
) -> list[ScheduleRow]:
    """Expand approved prescription items into concrete UTC-anchored dose
    events for the rolling window [today, today + horizon_days].

    `overrides`, when given, substitutes one or more routine anchors for a
    single day only (see DayAnchorOverrides) — every other day in the same
    call still uses the permanent `routine`. This goes through the exact
    same _validate_min_gap/_validate_cross_day_gaps calls as any other row
    below; there is no separate validation path for an overridden day.
    """
    validate_prescription_inputs(items)
    tz = ZoneInfo(patient_timezone)
    rows: list[ScheduleRow] = []
    minimums: dict[uuid.UUID, int] = {}

    for item in items:
        item_range = _item_horizon(item, today, horizon_days, max_treatment_days)
        if item_range is None:
            continue
        range_start, range_end = item_range
        min_gap = item.minimum_interval_minutes or default_min_gap_minutes
        minimums[item.id] = min_gap

        day = _first_dosing_day(range_start, item.start_date, item.interval_days)
        while day <= range_end:
            day_overrides = overrides.get(day) if overrides else None
            day_routine = replace(routine, **day_overrides) if day_overrides else routine
            day_slots = _candidate_slots_for_day(item, day_routine, day)
            for dose_field, local_dt in _validate_min_gap(day_slots, min_gap):
                utc_dt = local_dt.replace(tzinfo=tz).astimezone(UTC)
                # _candidate_slots_for_day includes only non-null, positive
                # Decimal values; the cast records that invariant for static
                # type checkers without changing the deterministic algorithm.
                dose_value = cast(Decimal, getattr(item, dose_field))
                rows.append(
                    ScheduleRow(
                        prescription_item_id=item.id,
                        medication_id=item.medication_id,
                        dose_slot=_DOSE_SLOT_NAMES[dose_field],
                        dose_value=dose_value,
                        dose_unit=item.dose_unit,
                        meal_relation=_normalize_meal_relation(item.meal_relation),
                        original_scheduled_at=utc_dt,
                        current_scheduled_at=utc_dt,
                        is_critical=item.is_critical,
                    )
                )
            day += timedelta(days=item.interval_days)

    _validate_cross_day_gaps(rows, minimums)
    return rows
