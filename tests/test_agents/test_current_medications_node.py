from unittest.mock import AsyncMock

import pytest

from src.agents.graph import _route_after_classify_intent
from src.agents.nodes import current_medications_node as module


def test_my_medications_intent_has_deterministic_database_route():
    assert _route_after_classify_intent({"intent": "ask_my_medications"}) == "current_medications"


def test_explain_and_next_dose_have_deterministic_routes():
    assert _route_after_classify_intent({"intent": "explain_my_medications"}) == "explain_my_medications"
    assert _route_after_classify_intent({"intent": "ask_next_dose"}) == "next_dose"
    assert _route_after_classify_intent({"intent": "ask_schedule"}) == "today_schedule"
    assert _route_after_classify_intent({"intent": "ask_scheduled_drug_info"}) == "scheduled_drug_info"


@pytest.mark.asyncio
async def test_current_medications_node_formats_database_result(monkeypatch):
    monkeypatch.setattr(
        module,
        "get",
        AsyncMock(
            return_value={
                "as_of": "2026-08-25",
                "medications": [
                    {
                        "display_name": "Amlodipin 5mg",
                        "dose_unit": "viên",
                        "morning_dose": 1,
                        "noon_dose": None,
                        "evening_dose": None,
                        "bedtime_dose": None,
                        "instructions": "Uống sau ăn",
                    }
                ],
            }
        ),
    )

    result = await module.current_medications_node({})
    answer = result["messages"][0].content

    assert "Amlodipin 5mg" in answer
    assert "sáng 1 viên" in answer
    assert "Uống sau ăn" in answer
    module.get.assert_awaited_once_with("/patients/me/medications/current")
