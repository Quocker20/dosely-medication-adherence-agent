from unittest.mock import AsyncMock

import pytest

from src.agents.nodes import today_schedule_node as module
from src.agents.nodes.next_dose_node import format_dose_value


def test_format_dose_value_does_not_present_one_as_one_thousand():
    assert format_dose_value("1.000") == "1"
    assert format_dose_value("1.500") == "1.5"
    assert format_dose_value(2) == "2"


@pytest.mark.asyncio
async def test_today_schedule_reads_same_patient_and_device_date_as_app(monkeypatch):
    get = AsyncMock(
        return_value={
            "date": "2026-08-29",
            "timezone": "Asia/Ho_Chi_Minh",
            "doses": [
                {
                    "current_scheduled_at": "2026-08-29T16:30:00Z",
                    "medication_name": "A-CN Gel",
                    "dose_value": "1.000",
                    "dose_unit": "viên",
                    "status": "PENDING",
                }
            ],
        }
    )
    monkeypatch.setattr(module, "get", get)

    result = await module.today_schedule_node(
        {"patient_id": "patient-123", "client_date": "2026-08-29"}
    )

    get.assert_awaited_once_with(
        "/patients/patient-123/schedules", params={"date": "2026-08-29"}
    )
    answer = result["messages"][0].content
    assert "23:30" in answer
    assert "1 viên" in answer
    assert "1.000 viên" not in answer


@pytest.mark.asyncio
async def test_today_schedule_empty_is_not_a_backend_error(monkeypatch):
    monkeypatch.setattr(
        module,
        "get",
        AsyncMock(return_value={"date": "2026-08-29", "doses": []}),
    )
    result = await module.today_schedule_node(
        {"patient_id": "patient-123", "client_date": "2026-08-29"}
    )
    assert "chưa có lịch" in result["messages"][0].content
