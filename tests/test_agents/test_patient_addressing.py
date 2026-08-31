from datetime import date
from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.messages import AIMessage

from src.agents.patient_addressing import get_patient_address, resolve_patient_address
from src.modules.agents.service import ChatService
from src.modules.planning.core.backend_client import BackendAPIError


@pytest.mark.parametrize(
    ("dob", "sex", "expected"),
    [
        ("1966-08-29", "MALE", "bác"),
        ("1988-03-12", "FEMALE", "chị"),
        ("1988-03-12", "MALE", "anh"),
        ("2012-01-01", "FEMALE", "bạn"),
        (None, "MALE", "bạn"),
        ("1988-03-12", "OTHER", "bạn"),
    ],
)
def test_resolve_patient_address(dob, sex, expected):
    assert resolve_patient_address(
        {"dob": dob, "sex": sex}, date(2026, 8, 29)
    ) == expected


@pytest.mark.asyncio
async def test_get_patient_address_uses_authenticated_profile_once():
    payload = {
        "profile": {
            "user_id": "patient-123",
            "dob": "1988-03-12",
            "sex": "FEMALE",
        }
    }
    with patch(
        "src.agents.patient_addressing.get", new=AsyncMock(return_value=payload)
    ) as mock_get:
        result = await get_patient_address("patient-123", date(2026, 8, 29))
    assert result == "chị"
    mock_get.assert_awaited_once_with("/patients/me/profile")


@pytest.mark.asyncio
async def test_get_patient_address_falls_back_when_backend_unavailable():
    with patch(
        "src.agents.patient_addressing.get",
        new=AsyncMock(side_effect=BackendAPIError(503, "offline")),
    ):
        assert await get_patient_address("patient-123") == "bạn"


@pytest.mark.asyncio
async def test_get_patient_address_rejects_cross_patient_profile():
    payload = {
        "profile": {
            "user_id": "other-patient",
            "dob": "1960-01-01",
            "sex": "MALE",
        }
    }
    with patch("src.agents.patient_addressing.get", new=AsyncMock(return_value=payload)):
        assert await get_patient_address("patient-123", date(2026, 8, 29)) == "bạn"


@pytest.mark.asyncio
async def test_chat_loads_address_once_and_puts_only_vocative_in_agent_state():
    address_get = AsyncMock(return_value="chị")
    invoke = AsyncMock(
        return_value={
            "messages": [AIMessage(content="Xin chào chị")],
            "intent": "general",
        }
    )
    with (
        patch("src.modules.agents.service.get_patient_address", new=address_get),
        patch("src.modules.agents.service.agent.ainvoke", new=invoke),
    ):
        response, _ = await ChatService()._run_agent(
            "Xin chào", "patient-123", date(2026, 8, 29)
        )

    assert response == "Xin chào chị"
    address_get.assert_awaited_once_with("patient-123", date(2026, 8, 29))
    state = invoke.await_args.args[0]
    assert state["patient_address"] == "chị"
    assert "profile" not in state
