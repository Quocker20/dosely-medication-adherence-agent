"""Wire-level contract of the agent's write tools against the backend.

These calls used to be rejected outright: the backend requires an
Idempotency-Key on every adherence/alert write and the tools sent none, so
`record_dose_action` and every automatic Red Alert returned 422 — the alert
path swallowed it via its fail-open handler and reported success-shaped text.
"""

from datetime import UTC, date, datetime
from unittest.mock import AsyncMock, patch

import pytest

from src.agents.tools.idempotency import alert_key, dose_action_key
from src.agents.tools.safety_tools import _send_alert, _triggered_by_type
from src.agents.tools.schedule_tools import record_dose_action


class TestIdempotencyKeys:
    def test_same_dose_action_on_same_day_yields_same_key(self):
        """A retried tool call must replay the original log, not add a second."""
        day = date(2026, 8, 14)
        assert dose_action_key("dose-1", "TAKEN", day) == dose_action_key("dose-1", "TAKEN", day)

    def test_action_is_case_insensitive(self):
        day = date(2026, 8, 14)
        assert dose_action_key("dose-1", "taken", day) == dose_action_key("dose-1", "TAKEN", day)

    def test_different_action_on_same_dose_yields_different_key(self):
        day = date(2026, 8, 14)
        assert dose_action_key("dose-1", "TAKEN", day) != dose_action_key("dose-1", "SKIPPED", day)

    def test_same_dose_on_a_later_day_yields_different_key(self):
        assert dose_action_key("dose-1", "TAKEN", date(2026, 8, 14)) != dose_action_key(
            "dose-1", "TAKEN", date(2026, 8, 15)
        )

    def test_alert_key_collapses_repeats_inside_the_bucket(self):
        """Patient restating one symptom must not page the doctor twice."""
        first = datetime(2026, 8, 14, 10, 0, 0, tzinfo=UTC)
        again = datetime(2026, 8, 14, 10, 3, 30, tzinfo=UTC)
        reason = "SEVERE_SYMPTOM: tức ngực"
        assert alert_key("p1", reason, first) == alert_key("p1", reason, again)

    def test_alert_key_reopens_after_the_bucket(self):
        """Dedup has to stay bounded — the same symptom later is a new event."""
        first = datetime(2026, 8, 14, 10, 0, 0, tzinfo=UTC)
        later = datetime(2026, 8, 14, 10, 30, 0, tzinfo=UTC)
        reason = "SEVERE_SYMPTOM: tức ngực"
        assert alert_key("p1", reason, first) != alert_key("p1", reason, later)

    def test_alert_key_is_per_patient(self):
        moment = datetime(2026, 8, 14, 10, 0, 0, tzinfo=UTC)
        reason = "SEVERE_SYMPTOM: tức ngực"
        assert alert_key("p1", reason, moment) != alert_key("p2", reason, moment)


class TestTriggeredByTypeMapping:
    """Alerts the agent detects must not be filed as button presses — the
    doctor's dashboard cannot otherwise tell a tap from a detection."""

    def test_severe_symptom_reason_maps_to_severe_symptom(self):
        assert _triggered_by_type("SEVERE_SYMPTOM: tức ngực") == "SEVERE_SYMPTOM"

    def test_missed_doses_reason_maps_to_missed_doses(self):
        assert _triggered_by_type("MISSED_DOSES") == "MISSED_DOSES"

    def test_unknown_reason_falls_back_to_sos_button(self):
        assert _triggered_by_type("bệnh nhân bấm nút") == "SOS_BUTTON"

    def test_mapped_values_are_all_accepted_by_the_db_constraint(self):
        """ck_alerts_triggered_by_type (migration 0009) — a value outside this
        set fails at INSERT, i.e. the alert is lost."""
        allowed = {"SOS_BUTTON", "SEVERE_SYMPTOM", "MISSED_DOSES"}
        for reason in ("SEVERE_SYMPTOM: khó thở", "MISSED_DOSES", "gì đó lạ"):
            assert _triggered_by_type(reason) in allowed


@pytest.mark.asyncio
async def test_record_dose_action_sends_idempotency_key():
    with patch("src.agents.tools.schedule_tools.post", new=AsyncMock(return_value={"id": "log-1"})) as mock_post:
        await record_dose_action.ainvoke({"scheduled_dose_id": "dose-1", "action": "taken", "note": "ngủ quên"})

    kwargs = mock_post.call_args.kwargs
    assert kwargs["headers"]["Idempotency-Key"] == dose_action_key("dose-1", "TAKEN")
    assert kwargs["json"]["action"] == "TAKEN"
    assert kwargs["json"]["payload"] == {"note": "ngủ quên"}


@pytest.mark.asyncio
async def test_send_alert_sends_key_and_structured_severity():
    """severity/triggered_by_type belong in their own columns, not buried in the
    message string where no query can filter on them."""
    with patch("src.agents.tools.safety_tools.post", new=AsyncMock(return_value={"id": "alert-1"})) as mock_post:
        await _send_alert("p1", "SEVERE_SYMPTOM: tức ngực", "HIGH", "tôi thấy tức ngực")

    args, kwargs = mock_post.call_args
    assert args[0] == "/patients/p1/sos"
    assert kwargs["json"]["triggered_by_type"] == "SEVERE_SYMPTOM"
    assert kwargs["json"]["severity"] == "HIGH"
    assert kwargs["headers"]["Idempotency-Key"]
