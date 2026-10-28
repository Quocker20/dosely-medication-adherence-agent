"""SEC-08: /chat/voice size and content-type limits."""

from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.messages import AIMessage

from src.core.config import get_settings
from src.core.security import create_access_token

PATIENT_ID = "11111111-1111-1111-1111-111111111111"
URL = "/api/v1/chat/voice"


def _headers() -> dict[str, str]:
    token = create_access_token(user_id=PATIENT_ID, role="PATIENT", phone_number="+84900000001")
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def small_limit(monkeypatch):
    monkeypatch.setattr(get_settings(), "voice_max_upload_bytes", 1024)


def test_default_limit_is_10_mb():
    assert get_settings().voice_max_upload_bytes == 10 * 1024 * 1024


@pytest.mark.asyncio
async def test_oversized_audio_is_413(client, small_limit):
    files = {"audio": ("rec.webm", b"x" * 2048, "audio/webm")}
    response = await client.post(URL, files=files, headers=_headers())
    assert response.status_code == 413


@pytest.mark.asyncio
async def test_non_audio_content_type_is_415(client, small_limit):
    files = {"audio": ("rec.exe", b"MZ", "application/x-msdownload")}
    response = await client.post(URL, files=files, headers=_headers())
    assert response.status_code == 415


@pytest.mark.asyncio
async def test_huge_content_length_rejected_before_parsing(client, small_limit):
    # Declared body far above limit + multipart margin -> rejected by the ASGI guard.
    files = {"audio": ("rec.webm", b"x" * (200 * 1024), "audio/webm")}
    response = await client.post(URL, files=files, headers=_headers())
    assert response.status_code == 413


@pytest.mark.asyncio
@pytest.mark.parametrize("ctype", ["audio/webm", "audio/webm;codecs=opus", "AUDIO/MP4", "audio/mpeg"])
async def test_audio_types_within_limit_pass_through(client, ctype):
    files = {"audio": ("rec.webm", b"fake-audio", ctype)}
    with (
        patch("src.modules.agents.chat_service.transcribe_audio", new=AsyncMock(return_value="xin chào")),
        patch("src.modules.agents.chat_service.synthesize_speech", new=AsyncMock(return_value=b"mp3")),
        patch("src.modules.agents.chat_service.agent") as mock_agent,
    ):
        mock_agent.ainvoke = AsyncMock(
            return_value={"messages": [AIMessage(content="ok")], "intent": "general", "escalated": False}
        )
        response = await client.post(URL, files=files, headers=_headers())
    assert response.status_code == 200
