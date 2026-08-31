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
    assert "23:30 - A-CN Gel — 1 viên - Chưa uống" in answer
    assert "PENDING" not in answer


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


@pytest.mark.asyncio
async def test_missed_morning_question_filters_status_and_period(monkeypatch):
    monkeypatch.setattr(module, "get", AsyncMock(return_value={
        "date": "2026-08-29",
        "timezone": "Asia/Bangkok",
        "doses": [
            {"current_scheduled_at": "2026-08-29T07:00:00+07:00", "medication_name": "Missed AM", "status": "MISSED"},
            {"current_scheduled_at": "2026-08-29T08:00:00+07:00", "medication_name": "Taken AM", "status": "TAKEN"},
            {"current_scheduled_at": "2026-08-29T19:00:00+07:00", "medication_name": "Missed PM", "status": "MISSED"},
        ],
    }))
    result = await module.today_schedule_node({
        "patient_id": "patient-123", "client_date": "2026-08-29",
        "intent_analysis": {"topics": ["dose_status"], "dose_period": "morning"},
    })
    answer = result["messages"][0].content
    assert "Missed AM" in answer
    assert "Taken AM" not in answer
    assert "Missed PM" not in answer


@pytest.mark.asyncio
async def test_today_schedule_renders_taken_and_not_taken_in_vietnamese(monkeypatch):
    monkeypatch.setattr(module, "get", AsyncMock(return_value={
        "date": "2026-08-30",
        "timezone": "Asia/Bangkok",
        "doses": [
            {"current_scheduled_at": "2026-08-30T07:00:00+07:00", "medication_name": "Paracetamol", "status": "TAKEN"},
            {"current_scheduled_at": "2026-08-30T12:00:00+07:00", "medication_name": "Amoxicillin", "status": "PENDING"},
            {"current_scheduled_at": "2026-08-30T19:00:00+07:00", "medication_name": "Metformin", "status": "MISSED"},
        ],
    }))

    result = await module.today_schedule_node({
        "patient_id": "patient-123", "client_date": "2026-08-30"
    })
    answer = result["messages"][0].content

    assert "07:00 - Paracetamol - Đã uống" in answer
    assert "12:00 - Amoxicillin - Chưa uống" in answer
    assert "19:00 - Metformin - Chưa uống (đã quá giờ)" in answer
    assert all(raw not in answer for raw in ("TAKEN", "PENDING", "MISSED"))
