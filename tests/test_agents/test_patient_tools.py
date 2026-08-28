import json
from unittest.mock import AsyncMock, patch

import pytest

from src.agents.tools.patient_tools import get_patient_profile


@pytest.mark.asyncio
async def test_get_patient_profile_returns_profile_demographics_for_addressing():
    payload = {
        "profile": {
            "user_id": "patient-123",
            "name": "Nguyen Thi A",
            "dob": "1988-03-12",
            "sex": "FEMALE",
            "timezone": "Asia/Ho_Chi_Minh",
            "emergency_note": None,
        },
        "routine": {
            "wake_time": "06:30:00",
            "breakfast_time": "07:00:00",
            "lunch_time": "11:30:00",
            "dinner_time": "18:00:00",
            "sleep_time": "22:00:00",
        },
    }

    with patch("src.agents.tools.patient_tools.get", new=AsyncMock(return_value=payload)) as mock_get:
        result = await get_patient_profile.ainvoke({"patient_id": "patient-123"})

    mock_get.assert_awaited_once_with("/patients/me/profile")
    decoded = json.loads(result)
    assert decoded["profile"]["dob"] == "1988-03-12"
    assert decoded["profile"]["sex"] == "FEMALE"
    assert decoded["routine"]["wake_time"] == "06:30:00"


@pytest.mark.asyncio
async def test_get_patient_profile_rejects_mismatched_patient_context():
    payload = {"profile": {"user_id": "other-patient"}}

    with patch("src.agents.tools.patient_tools.get", new=AsyncMock(return_value=payload)):
        result = await get_patient_profile.ainvoke({"patient_id": "patient-123"})

    assert "patient_id không khớp" in result
