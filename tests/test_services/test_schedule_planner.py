import uuid
from datetime import date, time
from decimal import Decimal

from src.modules.agents.planner import PlannableItem, RoutineTimes, expand_schedule


def test_min_gap_keeps_exact_slot_and_dose_snapshot() -> None:
    item_id = uuid.uuid4()
    medication_id = uuid.uuid4()
    item = PlannableItem(
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

    rows = expand_schedule(
        items=[item],
        routine=RoutineTimes(breakfast=time(7, 0), lunch=time(7, 10)),
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
    assert all(row.prescription_item_id == item_id for row in rows)
    assert all(row.medication_id == medication_id for row in rows)
    assert all(row.dose_unit == "tablet" for row in rows)
    assert all(row.meal_relation == "WITH_MEAL" for row in rows)
