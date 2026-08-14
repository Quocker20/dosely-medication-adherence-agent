"""Deterministic dose-schedule expansion — planning is code, not an LLM call
(src/core/config.py: "luật lâm sàng chạy bằng code xác định"). Pure functions:
no DB, no I/O, no wall-clock reads — `today` is always passed in, so this is
unit-testable without mocking anything.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from typing import List, Optional
from zoneinfo import ZoneInfo

_ANCHOR_FALLBACKS: dict[str, time] = {
    "wake": time(6, 0),
    "breakfast": time(7, 0),
    "lunch": time(12, 0),
    "dinner": time(18, 0),
    "sleep": time(22, 0),
}

# (dose column, routine anchor key, fixed offset minutes | None = derive from meal_relation)
_DOSE_SLOTS: tuple[tuple[str, str, Optional[int]], ...] = (
    ("morning_dose", "breakfast", None),
    ("noon_dose", "lunch", None),
    ("evening_dose", "dinner", None),
    ("bedtime_dose", "sleep", -30),
)

_MEAL_OFFSET_MINUTES: dict[Optional[str], int] = {
    "BEFORE_MEAL": -30,
    "AFTER_MEAL": 30,
    "WITH_MEAL": 0,
    None: 0,
}


@dataclass(frozen=True)
class RoutineTimes:
    """Plain snapshot of a patient's routine — decoupled from the ORM model
    so this module never touches the DB. wake is accepted for symmetry with
    the schema even though no dose slot anchors to it today."""

    wake: Optional[time] = None
    breakfast: Optional[time] = None
    lunch: Optional[time] = None
    dinner: Optional[time] = None
    sleep: Optional[time] = None

    def anchor(self, key: str) -> time:
        value = getattr(self, key)
        return value if value is not None else _ANCHOR_FALLBACKS[key]


@dataclass(frozen=True)
class PlannableItem:
    """Plain snapshot of the PrescriptionItem fields the planner needs."""

    id: uuid.UUID
    morning_dose: Optional[Decimal]
    noon_dose: Optional[Decimal]
    evening_dose: Optional[Decimal]
    bedtime_dose: Optional[Decimal]
    meal_relation: Optional[str]
    minimum_interval_minutes: Optional[int]
    start_date: date
    end_date: Optional[date]


@dataclass(frozen=True)
class ScheduleRow:
    prescription_item_id: uuid.UUID
    original_scheduled_at: datetime
    current_scheduled_at: datetime
    status: str = "PENDING"
    snooze_count: int = 0


class FrequencyGuardrailError(ValueError):
    """Raised by validate_frequency_guardrails when a PlannableItem requests
    more doses/day than settings.max_frequency_per_day allows. A distinct
    type (not a bare ValueError) so SchedulingService.execute_run's
    error_code (type(exc).__name__) is meaningful on GET /agent-runs/{id}
    rather than a generic 'ValueError'."""


def validate_frequency_guardrails(items: List[PlannableItem], max_per_day: int) -> None:
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
) -> Optional[tuple[date, date]]:
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


def _slot_local_dt(day: date, anchor: time, offset_minutes: int) -> datetime:
    """Combine day + anchor time + offset as a naive local datetime, letting
    timedelta arithmetic carry a cross-midnight offset (e.g. sleep_time
    00:15 with a -30m bedtime offset lands on the previous day) instead of
    wrapping time-of-day arithmetic by hand."""
    return datetime.combine(day, anchor) + timedelta(minutes=offset_minutes)


def _candidate_slots_for_day(item: PlannableItem, routine: RoutineTimes, day: date) -> List[tuple[str, datetime]]:
    slots: List[tuple[str, datetime]] = []
    for dose_field, anchor_key, fixed_offset in _DOSE_SLOTS:
        dose_value = getattr(item, dose_field)
        if dose_value is None or dose_value <= 0:
            continue
        offset = (
            fixed_offset
            if fixed_offset is not None
            else _MEAL_OFFSET_MINUTES.get(item.meal_relation, 0)
        )
        local_dt = _slot_local_dt(day, routine.anchor(anchor_key), offset)
        slots.append((dose_field, local_dt))
    return slots


def _apply_min_gap(slots: List[tuple[str, datetime]], min_gap_minutes: int) -> List[datetime]:
    """Push a slot forward (never drop it) when it falls closer than
    min_gap_minutes after the previous one for this same item/day — a
    prescribed dose must still happen, just not too close to the last."""
    times = sorted(dt for _, dt in slots)
    adjusted: List[datetime] = []
    for dt in times:
        if adjusted and (dt - adjusted[-1]) < timedelta(minutes=min_gap_minutes):
            dt = adjusted[-1] + timedelta(minutes=min_gap_minutes)
        adjusted.append(dt)
    return adjusted


def expand_schedule(
    items: List[PlannableItem],
    routine: RoutineTimes,
    patient_timezone: str,
    today: date,
    horizon_days: int,
    default_min_gap_minutes: int,
    max_treatment_days: int,
) -> List[ScheduleRow]:
    """Expand approved prescription items into concrete UTC-anchored dose
    events for the rolling window [today, today + horizon_days]."""
    tz = ZoneInfo(patient_timezone)
    rows: List[ScheduleRow] = []

    for item in items:
        item_range = _item_horizon(item, today, horizon_days, max_treatment_days)
        if item_range is None:
            continue
        range_start, range_end = item_range
        min_gap = item.minimum_interval_minutes or default_min_gap_minutes

        day = range_start
        while day <= range_end:
            day_slots = _candidate_slots_for_day(item, routine, day)
            for local_dt in _apply_min_gap(day_slots, min_gap):
                utc_dt = local_dt.replace(tzinfo=tz).astimezone(timezone.utc)
                rows.append(
                    ScheduleRow(
                        prescription_item_id=item.id,
                        original_scheduled_at=utc_dt,
                        current_scheduled_at=utc_dt,
                    )
                )
            day += timedelta(days=1)

    return rows
