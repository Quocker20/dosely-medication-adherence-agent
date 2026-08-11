import pytest

from src.agents.tools.safety_tools import (
    count_missed_dose_streak,
    match_severe_symptom_keyword,
    trigger_red_alert,
)


class TestMatchSevereSymptomKeyword:
    def test_matches_known_keyword(self):
        assert match_severe_symptom_keyword("tôi thấy tức ngực quá") == "tức ngực"

    def test_matches_case_insensitive(self):
        assert match_severe_symptom_keyword("TỨC NGỰC dữ lắm") == "tức ngực"

    def test_no_match_on_benign_text(self):
        assert match_severe_symptom_keyword("hôm nay hơi mệt vì đi bộ nhiều") is None


class TestCountMissedDoseStreak:
    def test_counts_trailing_missed_streak(self):
        doses = [
            {"status": "TAKEN"},
            {"status": "SKIPPED"},
            {"status": "MISSED"},
            {"status": "SKIPPED"},
        ]
        assert count_missed_dose_streak(doses) == 3

    def test_stops_at_first_non_missed_from_end(self):
        doses = [
            {"status": "SKIPPED"},
            {"status": "SKIPPED"},
            {"status": "TAKEN"},
        ]
        assert count_missed_dose_streak(doses) == 0

    def test_empty_list(self):
        assert count_missed_dose_streak([]) == 0


@pytest.mark.asyncio
async def test_trigger_red_alert_fails_open_on_stubbed_send():
    # _send_alert is stubbed (no real backend endpoint confirmed yet) — the
    # tool must never raise, and must say clearly that it failed.
    result = await trigger_red_alert.ainvoke(
        {
            "patient_id": "p1",
            "reason": "MISSED_DOSES",
            "severity": "HIGH",
            "evidence": "3 liều liên tiếp bị bỏ",
        }
    )
    assert "LỖI NGHIÊM TRỌNG" in result
