import uuid
from datetime import UTC, date, datetime, time
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from src.modules.agents.planner import (
    InvalidPrescriptionTimingError,
    MissingRoutineAnchorError,
    PlannableItem,
    RetainedDoseSnapshot,
    RoutineTimes,
    ScheduleConstraintError,
    ScheduleRow,
    expand_schedule,
    reconcile_reschedule_candidates,
    validate_candidate_boundaries,
)


def _item(**overrides) -> PlannableItem:
    item_id = uuid.uuid4()
    medication_id = uuid.uuid4()
    values = dict(
        id=item_id,
        medication_id=medication_id,
        dose_unit="tablet",
        morning_dose=Decimal("1"),
        noon_dose=Decimal("2"),
        evening_dose=None,
        bedtime_dose=None,
        meal_relation="with_meal",
        minimum_interval_minutes=60,
        start_date=date(2026, 8, 14),
        end_date=date(2026, 8, 14),
    )
    values.update(overrides)
    return PlannableItem(**values)


def test_min_gap_conflict_requires_review_instead_of_moving_slot() -> None:
    item = _item()

    with pytest.raises(ScheduleConstraintError):
        expand_schedule(
            items=[item],
            routine=RoutineTimes(breakfast=time(7, 0), lunch=time(7, 10)),
            patient_timezone="Asia/Ho_Chi_Minh",
            today=date(2026, 8, 14),
            horizon_days=0,
            default_min_gap_minutes=30,
            max_treatment_days=30,
        )


def test_valid_slots_keep_exact_time_and_dose_snapshot() -> None:
    item = _item()

    rows = expand_schedule(
        items=[item],
        routine=RoutineTimes(breakfast=time(7, 0), lunch=time(8, 0)),
        patient_timezone="Asia/Ho_Chi_Minh",
        today=date(2026, 8, 14),
        horizon_days=0,
        default_min_gap_minutes=30,
        max_treatment_days=30,
    )

    assert [(row.dose_slot, row.dose_value) for row in rows] == [
        ("MORNING", Decimal("1")),
        ("NOON", Decimal("2")),
    ]
    assert rows[0].current_scheduled_at.isoformat() == "2026-08-14T00:00:00+00:00"
    assert rows[1].current_scheduled_at.isoformat() == "2026-08-14T01:00:00+00:00"
    assert all(row.prescription_item_id == item.id for row in rows)
    assert all(row.medication_id == item.medication_id for row in rows)
    assert all(row.dose_unit == "tablet" for row in rows)
    assert all(row.meal_relation == "WITH_MEAL" for row in rows)


def test_missing_required_routine_anchor_requires_review() -> None:
    item = _item(noon_dose=None)

    with pytest.raises(MissingRoutineAnchorError):
        expand_schedule(
            items=[item],
            routine=RoutineTimes(),
            patient_timezone="Asia/Ho_Chi_Minh",
            today=date(2026, 8, 14),
            horizon_days=0,
            default_min_gap_minutes=30,
            max_treatment_days=30,
        )


def test_min_gap_is_validated_across_day_boundary() -> None:
    item = _item(
        morning_dose=Decimal("1"),
        noon_dose=None,
        evening_dose=None,
        bedtime_dose=Decimal("1"),
        meal_relation=None,
        minimum_interval_minutes=600,
        end_date=date(2026, 8, 15),
    )

    with pytest.raises(ScheduleConstraintError):
        expand_schedule(
            items=[item],
            routine=RoutineTimes(breakfast=time(7, 0), sleep=time(23, 30)),
            patient_timezone="Asia/Ho_Chi_Minh",
            today=date(2026, 8, 14),
            horizon_days=1,
            default_min_gap_minutes=30,
            max_treatment_days=30,
        )


@pytest.mark.parametrize(
    "overrides",
    [
        {"morning_dose": Decimal("0"), "noon_dose": None},
        {"morning_dose": None, "noon_dose": None},
        {"meal_relation": "SOMETIME_AROUND_FOOD"},
        {"minimum_interval_minutes": 0},
        {"minimum_interval_minutes": -1},
    ],
)
def test_invalid_approved_item_requires_review(overrides: dict) -> None:
    with pytest.raises(InvalidPrescriptionTimingError):
        expand_schedule(
            items=[_item(**overrides)],
            routine=RoutineTimes(breakfast=time(7, 0), lunch=time(12, 0)),
            patient_timezone="Asia/Ho_Chi_Minh",
            today=date(2026, 8, 14),
            horizon_days=0,
            default_min_gap_minutes=30,
            max_treatment_days=30,
        )


def test_candidate_boundary_checks_retained_dose() -> None:
    item = _item(
        morning_dose=Decimal("1"),
        noon_dose=None,
        minimum_interval_minutes=600,
    )
    candidate_time = datetime(2026, 8, 14, 12, 0, tzinfo=UTC)
    candidate = expand_schedule(
        items=[item],
        routine=RoutineTimes(breakfast=time(19, 0)),
        patient_timezone="Asia/Ho_Chi_Minh",
        today=date(2026, 8, 14),
        horizon_days=0,
        default_min_gap_minutes=30,
        max_treatment_days=30,
    )[0]
    assert candidate.current_scheduled_at == candidate_time

    with pytest.raises(ScheduleConstraintError):
        validate_candidate_boundaries(
            items=[item],
            candidates=[candidate],
            retained_times={item.id: [datetime(2026, 8, 14, 8, 0, tzinfo=UTC)]},
            default_min_gap_minutes=30,
        )


def test_reschedule_does_not_duplicate_retained_slot_on_same_local_day() -> None:
    item = _item(
        morning_dose=Decimal("1"),
        noon_dose=None,
        minimum_interval_minutes=60,
    )
    candidate = expand_schedule(
        items=[item],
        routine=RoutineTimes(breakfast=time(19, 0)),
        patient_timezone="Asia/Ho_Chi_Minh",
        today=date(2026, 8, 14),
        horizon_days=0,
        default_min_gap_minutes=30,
        max_treatment_days=30,
    )[0]

    result = reconcile_reschedule_candidates(
        items=[item],
        candidates=[candidate],
        locked_schedule=[
            RetainedDoseSnapshot(
                prescription_item_id=item.id,
                dose_slot="MORNING",
                original_scheduled_at=datetime(2026, 8, 14, 8, 0, tzinfo=UTC),
                current_scheduled_at=datetime(2026, 8, 14, 8, 0, tzinfo=UTC),
                status="TAKEN",
            )
        ],
        now=datetime(2026, 8, 14, 10, 0, tzinfo=UTC),
        patient_timezone="Asia/Ho_Chi_Minh",
        default_min_gap_minutes=30,
    )

    assert result == []


def test_override_shifts_only_the_anchored_dose_slot_for_the_override_day() -> None:
    item = _item(
        morning_dose=None,
        noon_dose=None,
        evening_dose=Decimal("1"),
        bedtime_dose=Decimal("1"),
        meal_relation="WITH_MEAL",
        minimum_interval_minutes=60,
        end_date=date(2026, 8, 15),
    )
    override_day = date(2026, 8, 14)

    rows = expand_schedule(
        items=[item],
        routine=RoutineTimes(dinner=time(19, 0), sleep=time(23, 0)),
        patient_timezone="Asia/Ho_Chi_Minh",
        today=override_day,
        horizon_days=1,
        default_min_gap_minutes=30,
        max_treatment_days=30,
        overrides={override_day: {"dinner": time(20, 30)}},
    )

    evening_rows = [row for row in rows if row.dose_slot == "EVENING"]
    bedtime_rows = [row for row in rows if row.dose_slot == "BEDTIME"]
    assert evening_rows[0].current_scheduled_at.isoformat() == "2026-08-14T13:30:00+00:00"
    assert bedtime_rows[0].current_scheduled_at.isoformat() == "2026-08-14T15:30:00+00:00"
    # Day 2 (no override entry) falls back to the permanent routine unchanged.
    assert evening_rows[1].current_scheduled_at.isoformat() == "2026-08-15T12:00:00+00:00"
    assert bedtime_rows[1].current_scheduled_at.isoformat() == "2026-08-15T15:30:00+00:00"


def test_override_still_enforces_min_gap_and_raises_needs_review_error() -> None:
    item = _item(
        morning_dose=None,
        noon_dose=None,
        evening_dose=Decimal("1"),
        bedtime_dose=Decimal("1"),
        meal_relation="WITH_MEAL",
        minimum_interval_minutes=180,
    )
    override_day = date(2026, 8, 14)

    with pytest.raises(ScheduleConstraintError):
        expand_schedule(
            items=[item],
            routine=RoutineTimes(dinner=time(19, 0), sleep=time(23, 0)),
            patient_timezone="Asia/Ho_Chi_Minh",
            today=override_day,
            horizon_days=0,
            default_min_gap_minutes=30,
            max_treatment_days=30,
            # Dinner pushed to 22:00 leaves only 30 min before the 22:30
            # bedtime slot — well under the 180-minute minimum interval.
            overrides={override_day: {"dinner": time(22, 0)}},
        )


def test_no_overrides_argument_preserves_existing_behavior() -> None:
    item = _item()

    with_none = expand_schedule(
        items=[item],
        routine=RoutineTimes(breakfast=time(7, 0), lunch=time(8, 0)),
        patient_timezone="Asia/Ho_Chi_Minh",
        today=date(2026, 8, 14),
        horizon_days=0,
        default_min_gap_minutes=30,
        max_treatment_days=30,
    )
    with_empty_dict = expand_schedule(
        items=[item],
        routine=RoutineTimes(breakfast=time(7, 0), lunch=time(8, 0)),
        patient_timezone="Asia/Ho_Chi_Minh",
        today=date(2026, 8, 14),
        horizon_days=0,
        default_min_gap_minutes=30,
        max_treatment_days=30,
        overrides={},
    )

    assert with_none == with_empty_dict


def _bedtime_only_item(**overrides) -> PlannableItem:
    values = dict(
        morning_dose=None,
        noon_dose=None,
        evening_dose=None,
        bedtime_dose=Decimal("1"),
        meal_relation=None,
    )
    values.update(overrides)
    return _item(**values)


def test_post_midnight_sleep_time_anchors_the_bedtime_dose_to_the_next_day() -> None:
    """A patient whose permanent routine says they sleep at 01:00 means 01:00
    the following morning. Anchoring to the same calendar day put the dose ~23h
    early, where it landed in the past and was dropped entirely."""
    rows = expand_schedule(
        items=[_bedtime_only_item()],
        routine=RoutineTimes(sleep=time(1, 0)),
        patient_timezone="Asia/Ho_Chi_Minh",
        today=date(2026, 8, 14),
        horizon_days=0,
        default_min_gap_minutes=30,
        max_treatment_days=30,
    )

    # 01:00 on the 15th, minus the fixed 30-minute bedtime offset, in ICT.
    assert [row.dose_slot for row in rows] == ["BEDTIME"]
    assert rows[0].current_scheduled_at.isoformat() == "2026-08-14T17:30:00+00:00"


def test_evening_sleep_time_keeps_the_bedtime_dose_on_the_same_day() -> None:
    """Regression guard on the cutoff: only a pre-midday sleep time rolls over."""
    rows = expand_schedule(
        items=[_bedtime_only_item()],
        routine=RoutineTimes(sleep=time(23, 0)),
        patient_timezone="Asia/Ho_Chi_Minh",
        today=date(2026, 8, 14),
        horizon_days=0,
        default_min_gap_minutes=30,
        max_treatment_days=30,
    )

    assert rows[0].current_scheduled_at.isoformat() == "2026-08-14T15:30:00+00:00"


def test_override_to_a_post_midnight_sleep_time_also_rolls_over() -> None:
    """The same rule must hold when the post-midnight time arrives as a
    same-day override ("hôm nay tôi ngủ trễ, khoảng 1 giờ sáng") rather than
    from the permanent routine."""
    override_day = date(2026, 8, 14)

    rows = expand_schedule(
        items=[_bedtime_only_item()],
        routine=RoutineTimes(sleep=time(23, 0)),
        patient_timezone="Asia/Ho_Chi_Minh",
        today=override_day,
        horizon_days=0,
        default_min_gap_minutes=30,
        max_treatment_days=30,
        overrides={override_day: {"sleep": time(1, 0)}},
    )

    assert rows[0].current_scheduled_at.isoformat() == "2026-08-14T17:30:00+00:00"


def test_interval_days_one_matches_the_pre_feature_daily_behaviour() -> None:
    """interval_days=1 is the default and must reproduce exactly what
    expand_schedule did before this field existed — a pure regression check."""
    daily_item = _item(end_date=date(2026, 8, 17))
    explicit_item = _item(interval_days=1, end_date=date(2026, 8, 17))

    daily_rows = expand_schedule(
        items=[daily_item],
        routine=RoutineTimes(breakfast=time(7, 0), lunch=time(12, 0)),
        patient_timezone="Asia/Ho_Chi_Minh",
        today=date(2026, 8, 14),
        horizon_days=3,
        default_min_gap_minutes=30,
        max_treatment_days=30,
    )
    explicit_rows = expand_schedule(
        items=[explicit_item],
        routine=RoutineTimes(breakfast=time(7, 0), lunch=time(12, 0)),
        patient_timezone="Asia/Ho_Chi_Minh",
        today=date(2026, 8, 14),
        horizon_days=3,
        default_min_gap_minutes=30,
        max_treatment_days=30,
    )
    assert [r.current_scheduled_at for r in daily_rows] == [r.current_scheduled_at for r in explicit_rows]
    assert len(daily_rows) == 8  # 2 slots/day * 4 days (start_date fixed at 2026-08-14)


def test_every_other_day_regimen_skips_the_days_in_between() -> None:
    item = _item(
        morning_dose=Decimal("1"),
        noon_dose=None,
        start_date=date(2026, 8, 14),
        end_date=date(2026, 8, 20),
        interval_days=2,
    )

    rows = expand_schedule(
        items=[item],
        routine=RoutineTimes(breakfast=time(7, 0)),
        patient_timezone="Asia/Ho_Chi_Minh",
        today=date(2026, 8, 14),
        horizon_days=6,
        default_min_gap_minutes=30,
        max_treatment_days=30,
    )

    dosed_days = sorted({row.current_scheduled_at.astimezone(ZoneInfo("Asia/Ho_Chi_Minh")).date() for row in rows})
    assert [d.isoformat() for d in dosed_days] == ["2026-08-14", "2026-08-16", "2026-08-18", "2026-08-20"]


def test_every_other_day_regimen_mid_treatment_stays_phase_locked_to_start_date() -> None:
    """The bug Plan B's naive `day += interval_days from range_start` would
    have introduced: for a patient already partway through an every-other-day
    course, the dosing days must still land on start_date's own parity
    (odd days after 2026-08-01: 1, 3, 5, 7, 9, 11...), not on today's."""
    item = _item(
        morning_dose=Decimal("1"),
        noon_dose=None,
        start_date=date(2026, 8, 1),
        end_date=date(2026, 8, 20),
        interval_days=2,
    )
    today = date(2026, 8, 10)  # 9 days after start_date — an "off" day.

    rows = expand_schedule(
        items=[item],
        routine=RoutineTimes(breakfast=time(7, 0)),
        patient_timezone="Asia/Ho_Chi_Minh",
        today=today,
        horizon_days=4,
        default_min_gap_minutes=30,
        max_treatment_days=30,
    )

    dosed_days = sorted({row.current_scheduled_at.astimezone(ZoneInfo("Asia/Ho_Chi_Minh")).date() for row in rows})
    # Correct dosing days from start_date=Aug 1 with interval 2: 1,3,5,7,9,11,13...
    # The window [today=Aug10, today+4=Aug14] contains only Aug 11 and Aug 13.
    assert [d.isoformat() for d in dosed_days] == ["2026-08-11", "2026-08-13"]


def test_interval_days_below_one_requires_review() -> None:
    with pytest.raises(InvalidPrescriptionTimingError):
        expand_schedule(
            items=[_item(interval_days=0)],
            routine=RoutineTimes(breakfast=time(7, 0), lunch=time(12, 0)),
            patient_timezone="Asia/Ho_Chi_Minh",
            today=date(2026, 8, 14),
            horizon_days=0,
            default_min_gap_minutes=30,
            max_treatment_days=30,
        )


def test_cross_midnight_snooze_uses_original_day_for_dedup() -> None:
    item = _item(
        morning_dose=Decimal("1"),
        noon_dose=None,
        minimum_interval_minutes=60,
    )
    candidate_time = datetime(2026, 8, 15, 0, 30, tzinfo=UTC)
    candidate = ScheduleRow(
        prescription_item_id=item.id,
        medication_id=item.medication_id,
        dose_slot="MORNING",
        dose_value=Decimal("1"),
        dose_unit="tablet",
        meal_relation="WITH_MEAL",
        original_scheduled_at=candidate_time,
        current_scheduled_at=candidate_time,
    )

    result = reconcile_reschedule_candidates(
        items=[item],
        candidates=[candidate],
        locked_schedule=[
            RetainedDoseSnapshot(
                prescription_item_id=item.id,
                dose_slot="MORNING",
                original_scheduled_at=datetime(2026, 8, 14, 0, 30, tzinfo=UTC),
                current_scheduled_at=datetime(2026, 8, 14, 18, 30, tzinfo=UTC),
                status="PENDING",
            )
        ],
        now=datetime(2026, 8, 14, 20, 0, tzinfo=UTC),
        patient_timezone="Asia/Ho_Chi_Minh",
        default_min_gap_minutes=30,
    )

    assert result == [candidate]
