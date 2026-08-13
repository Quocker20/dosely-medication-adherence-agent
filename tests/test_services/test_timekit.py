from src.modules.planning.core.timekit import DAY_MINUTES, min_gap_minutes, shift, to_hhmm, to_minutes


def test_to_minutes_and_back():
    assert to_minutes("07:30") == 450
    assert to_hhmm(450) == "07:30"


def test_shift_wraps_around_midnight():
    assert shift("00:15", -30) == "23:45"
    assert shift("23:50", 20) == "00:10"


def test_min_gap_ignores_order():
    assert min_gap_minutes(["19:00", "07:00", "12:00"]) == 300


def test_min_gap_without_constraint():
    assert min_gap_minutes(["07:00"]) == DAY_MINUTES
    assert min_gap_minutes([]) == DAY_MINUTES
