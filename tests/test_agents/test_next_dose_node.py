from unittest.mock import AsyncMock

import pytest

from src.agents.nodes import next_dose_node as module
from src.modules.planning.core.backend_client import BackendAPIError


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ({"status": "NO_SCHEDULE", "local_date": "2026-08-27"}, "chưa có lịch"),
        ({"status": "NO_UPCOMING", "local_date": "2026-08-27"}, "không còn cữ nào"),
        (
            {
                "status": "UPCOMING",
                "local_date": "2026-08-27",
                "dose": {
                    "medication_name": "Metformin 500mg",
                    "current_scheduled_at": "2026-08-27T19:30:00+07:00",
                    "dose_value": 1,
                    "dose_unit": "viên",
                },
            },
            "Metformin 500mg lúc 19:30",
        ),
    ],
)
async def test_next_dose_states_are_distinct(monkeypatch, payload, expected):
    monkeypatch.setattr(module, "get", AsyncMock(return_value=payload))
    result = await module.next_dose_node({})
    assert expected in result["messages"][0].content
    module.get.assert_awaited_once_with("/patients/me/schedules/next")


@pytest.mark.asyncio
async def test_next_dose_backend_failure_is_not_reported_as_empty_schedule(monkeypatch):
    monkeypatch.setattr(
        module,
        "get",
        AsyncMock(side_effect=BackendAPIError(503, "offline")),
    )
    result = await module.next_dose_node({})
    answer = result["messages"][0].content
    assert "chưa thể kết nối" in answer
    assert "chưa có lịch" not in answer
