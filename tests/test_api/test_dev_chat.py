"""POST /dev/chat is the no-login local chatbot harness. It is gated by
APP_ENV=development AND ENABLE_LOCAL_CHAT_TEST, loopback only. It used to
reference get_settings without importing it, so every request raised NameError
(ruff F821) -- even the one that should have been a clean 404."""

import uuid
from unittest.mock import AsyncMock, patch

import pytest

from src.core.config import get_settings
from src.modules.agents.schemas import ChatResponse

URL = "/api/v1/dev/chat"


@pytest.fixture
def dev_chat_enabled(monkeypatch):
    settings = get_settings()
    patient_id = str(uuid.uuid4())
    monkeypatch.setattr(settings, "app_env", "development")
    monkeypatch.setattr(settings, "enable_local_chat_test", True)
    monkeypatch.setattr(settings, "dev_chat_patient_id", patient_id)
    return patient_id


@pytest.mark.asyncio
async def test_dev_chat_is_404_when_flag_is_off(client):
    response = await client.post(URL, json={"message": "Xin chào"})

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_dev_chat_is_404_outside_development_even_with_flag(client, dev_chat_enabled, monkeypatch):
    monkeypatch.setattr(get_settings(), "app_env", "production")

    response = await client.post(URL, json={"message": "Xin chào"})

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_dev_chat_answers_for_the_configured_patient(client, dev_chat_enabled):
    handle_text_chat = AsyncMock(return_value=ChatResponse(response="Xin chào"))
    with patch("src.modules.agents.service.ChatService.handle_text_chat", new=handle_text_chat):
        response = await client.post(URL, json={"message": "Xin chào"})

    assert response.status_code == 200
    assert response.json()["data"]["response"] == "Xin chào"
    assert handle_text_chat.await_args.kwargs["patient_id"] == dev_chat_enabled


@pytest.mark.asyncio
async def test_dev_chat_reports_missing_patient_config(client, dev_chat_enabled, monkeypatch):
    monkeypatch.setattr(get_settings(), "dev_chat_patient_id", "")

    response = await client.post(URL, json={"message": "Xin chào"})

    assert response.status_code == 503
