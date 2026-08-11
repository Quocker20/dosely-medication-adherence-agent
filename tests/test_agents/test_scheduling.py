from datetime import datetime

import pytest

from src.agents.scheduling import compute_schedule

ROUTINE = {
    "wake_time": "06:00:00",
    "breakfast_time": "07:00:00",
    "lunch_time": "12:00:00",
    "dinner_time": "18:30:00",
    "sleep_time": "22:00:00",
}


def _metformin(**overrides) -> dict:
    item = {
        "id": "item-1",
        "display_name": "Metformin 850mg",
        "dose_unit": "VIEN",
        "morning_dose": 1,
        "noon_dose": None,
        "evening_dose": 1,
        "bedtime_dose": None,
        "meal_relation": "AFTER_MEAL",
        "minimum_interval_minutes": None,
        "start_date": "2026-08-01",
        "end_date": None,
        "instructions": "Uống sau ăn",
    }
    item.update(overrides)
    return item


def test_two_daily_doses_offset_after_meal():
    doses = compute_schedule([_metformin()], ROUTINE, "2026-08-11")

    assert len(doses) == 2
    morning, evening = doses
    assert morning["slot"] == "morning"
    assert datetime.fromisoformat(morning["current_scheduled_at"]).time().isoformat() == "07:30:00"
    assert evening["slot"] == "evening"
    assert datetime.fromisoformat(evening["current_scheduled_at"]).time().isoformat() == "19:00:00"


def test_timezone_is_applied():
    doses = compute_schedule([_metformin()], ROUTINE, "2026-08-11", timezone="Asia/Ho_Chi_Minh")
    dt = datetime.fromisoformat(doses[0]["current_scheduled_at"])
    assert dt.utcoffset().total_seconds() == 7 * 3600


def test_four_times_a_day_with_tight_early_sleep_routine():
    """Eval case: thuốc 4 lần/ngày với routine ngủ sớm — không được sinh lịch
    vi phạm minimum_interval_minutes dù routine bị nén."""
    tight_routine = {
        "wake_time": "05:30:00",
        "breakfast_time": "06:00:00",
        "lunch_time": "07:30:00",  # rất gần bữa sáng
        "dinner_time": "09:00:00",  # ngủ sớm nên ăn tối sớm
        "sleep_time": "10:00:00",
    }
    item = _metformin(
        noon_dose=1,
        bedtime_dose=1,
        minimum_interval_minutes=240,  # tối thiểu 4h/cữ
        meal_relation="WITH_MEAL",
    )

    doses = compute_schedule([item], tight_routine, "2026-08-11")

    assert len(doses) == 4
    times = [datetime.fromisoformat(d["current_scheduled_at"]) for d in doses]
    for earlier, later in zip(times, times[1:]):
        assert (later - earlier).total_seconds() >= 240 * 60
    # Các cữ bị đẩy giờ phải được đánh dấu rõ ràng, không âm thầm.
    assert any(d.get("adjusted_for_min_interval") for d in doses[1:])


def test_minimum_interval_pushes_conflicting_dose():
    item = _metformin(minimum_interval_minutes=480)  # cần cách nhau 8h
    # breakfast 07:00 (sau ăn -> 07:30) và dinner 18:30 (sau ăn -> 19:00) đã
    # cách nhau > 8h nên dùng routine gần nhau hơn để ép xảy ra xung đột.
    close_routine = {**ROUTINE, "dinner_time": "10:00:00"}

    doses = compute_schedule([item], close_routine, "2026-08-11")

    morning, evening = doses
    gap = datetime.fromisoformat(evening["current_scheduled_at"]) - datetime.fromisoformat(
        morning["current_scheduled_at"]
    )
    assert gap.total_seconds() == 8 * 3600
    assert evening["adjusted_for_min_interval"] is True


def test_missing_routine_anchor_raises_clear_error():
    routine_without_dinner = {k: v for k, v in ROUTINE.items() if k != "dinner_time"}

    with pytest.raises(ValueError, match="dinner_time"):
        compute_schedule([_metformin()], routine_without_dinner, "2026-08-11")


def test_item_outside_date_range_is_excluded():
    item = _metformin(start_date="2026-09-01")  # chưa tới ngày bắt đầu

    doses = compute_schedule([item], ROUTINE, "2026-08-11")

    assert doses == []


def test_output_is_json_serializable():
    import json

    doses = compute_schedule([_metformin()], ROUTINE, "2026-08-11")
    json.dumps(doses)  # không raise
