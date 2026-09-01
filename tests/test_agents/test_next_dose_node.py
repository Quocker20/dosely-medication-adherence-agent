from unittest.mock import AsyncMock

import pytest
from langchain_core.messages import HumanMessage

from src.agents.nodes import next_dose_node as module
from src.modules.planning.core.backend_client import BackendAPIError

STATE = {
    "patient_id": "patient-123",
    "client_date": "2026-08-27",
    "client_datetime": "2026-08-27T18:00:00+07:00",
}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ({"date": "2026-08-27", "doses": []}, "chưa có lịch"),
        (
            {"date": "2026-08-27", "doses": [{"status": "TAKEN"}]},
            "không còn cữ nào",
        ),
        (
            {
                "date": "2026-08-27",
                "timezone": "Asia/Bangkok",
                "doses": [
                    {
                        "status": "PENDING",
                        "medication_name": "Metformin 500mg",
                        "current_scheduled_at": "2026-08-27T19:30:00+07:00",
                        "dose_value": "1.000",
                        "dose_unit": "viên",
                    }
                ],
            },
            "Metformin 500mg lúc 19:30, liều 1 viên",
        ),
    ],
)
async def test_next_dose_uses_app_schedule(monkeypatch, payload, expected):
    get = AsyncMock(return_value=payload)
    monkeypatch.setattr(module, "get", get)
    result = await module.next_dose_node(STATE)
    assert expected in result["messages"][0].content
    get.assert_awaited_once_with("/patients/patient-123/schedules", params={"date": "2026-08-27"})


@pytest.mark.asyncio
async def test_next_dose_backend_failure_is_not_reported_as_empty_schedule(monkeypatch):
    monkeypatch.setattr(module, "get", AsyncMock(side_effect=BackendAPIError(503, "offline")))
    result = await module.next_dose_node(STATE)
    answer = result["messages"][0].content
    assert "chưa thể kết nối" in answer
    assert "chưa có lịch" not in answer


@pytest.mark.asyncio
async def test_tomorrow_at_explicit_time_queries_tomorrow_not_today(monkeypatch):
    get = AsyncMock(
        return_value={
            "date": "2026-08-28",
            "timezone": "Asia/Bangkok",
            "doses": [
                {
                    "status": "PENDING",
                    "medication_name": "Paracetamol",
                    "current_scheduled_at": "2026-08-28T07:00:00+07:00",
                    "dose_value": 1,
                    "dose_unit": "viên",
                }
            ],
        }
    )
    monkeypatch.setattr(module, "get", get)
    state = {**STATE, "messages": [HumanMessage(content="7h sáng mai tôi phải uống gì không?")]}

    result = await module.next_dose_node(state)

    get.assert_awaited_once_with("/patients/patient-123/schedules", params={"date": "2026-08-28"})
    assert "Paracetamol" in result["messages"][0].content
