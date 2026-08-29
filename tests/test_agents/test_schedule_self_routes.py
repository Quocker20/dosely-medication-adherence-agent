import json
import uuid
from unittest.mock import AsyncMock

import pytest

from src.modules.agents.router import get_my_next_dose, get_my_today_schedule
from src.modules.agents.schemas import ActiveScheduleResponse, NextDoseResponse

PATIENT_ID = uuid.UUID("10000000-0000-0000-0000-000000000001")
CURRENT_USER = {"sub": str(PATIENT_ID), "role": "PATIENT"}


@pytest.mark.asyncio
async def test_today_route_uses_only_authenticated_patient_identity():
    service = AsyncMock()
    service.get_today_schedule_for_patient.return_value = ActiveScheduleResponse(
        patient_id=PATIENT_ID,
        date="2026-08-29",
        timezone="Asia/Ho_Chi_Minh",
        doses=[],
    )

    response = await get_my_today_schedule(CURRENT_USER, service)

    service.get_today_schedule_for_patient.assert_awaited_once_with(
        patient_id=PATIENT_ID,
        actor_payload=CURRENT_USER,
    )
    payload = json.loads(response.body)["data"]
    assert payload["patient_id"] == str(PATIENT_ID)
    assert payload["timezone"] == "Asia/Ho_Chi_Minh"


@pytest.mark.asyncio
async def test_next_route_returns_service_result_instead_of_empty_response():
    service = AsyncMock()
    service.get_next_dose_for_patient.return_value = NextDoseResponse(
        status="NO_UPCOMING",
        local_date="2026-08-29",
        timezone="Asia/Ho_Chi_Minh",
    )

    response = await get_my_next_dose(CURRENT_USER, service)

    service.get_next_dose_for_patient.assert_awaited_once_with(
        patient_id=PATIENT_ID,
        actor_payload=CURRENT_USER,
    )
    payload = json.loads(response.body)["data"]
    assert payload["status"] == "NO_UPCOMING"
