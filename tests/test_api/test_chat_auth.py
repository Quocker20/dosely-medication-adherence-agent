import uuid
from unittest.mock import AsyncMock, patch

import pytest

from src.core.security import create_access_token


PATIENT_ID = str(uuid.uuid4())


def _auth_headers(role: str = "PATIENT", user_id: str = PATIENT_ID) -> dict[str, str]:
    token = create_access_token(
        user_id=user_id,
        role=role,
        phone_number="+84901234567",
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_chat_requires_authentication(client):
    response = await client.post("/api/v1/chat", json={"message": "Xin chào"})

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_chat_rejects_non_patient_role(client):
    response = await client.post(
        "/api/v1/chat",
        json={"message": "Xin chào"},
        headers=_auth_headers(role="DOCTOR"),
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_chat_uses_authenticated_patient_and_ignores_legacy_client_id(client):
    run_agent = AsyncMock(return_value="Phản hồi an toàn")
    with patch("src.modules.agents.router._run_agent", new=run_agent):
        response = await client.post(
            "/api/v1/chat",
            json={
                "message": "Lịch thuốc hôm nay?",
                # Backward compatibility: an older app may still send this,
                # but it must never control the agent's patient context.
                "patient_id": str(uuid.uuid4()),
            },
            headers=_auth_headers(),
        )

    assert response.status_code == 200
    assert response.json() == {"response": "Phản hồi an toàn"}
    run_agent.assert_awaited_once_with("Lịch thuốc hôm nay?", PATIENT_ID)


@pytest.mark.asyncio
async def test_chat_voice_uses_authenticated_patient_without_form_patient_id(client):
    run_agent = AsyncMock(return_value="Đã kiểm tra lịch thuốc")
    with (
        patch(
            "src.modules.agents.router.transcribe_audio",
            new=AsyncMock(return_value="Tôi uống thuốc chưa?"),
        ),
        patch(
            "src.modules.agents.router.synthesize_speech",
            new=AsyncMock(return_value=b"mp3"),
        ),
        patch("src.modules.agents.router._run_agent", new=run_agent),
    ):
        response = await client.post(
            "/api/v1/chat/voice",
            files={"audio": ("question.m4a", b"audio", "audio/mp4")},
            headers=_auth_headers(),
        )

    assert response.status_code == 200
    assert response.json()["transcript"] == "Tôi uống thuốc chưa?"
    run_agent.assert_awaited_once_with("Tôi uống thuốc chưa?", PATIENT_ID)
