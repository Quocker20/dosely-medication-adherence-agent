import uuid
from datetime import UTC, date, datetime, time
from decimal import Decimal

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
