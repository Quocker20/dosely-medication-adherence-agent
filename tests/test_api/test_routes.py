from contextlib import ExitStack
from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.messages import AIMessage

from src.agents.nodes.classify_intent_node import IntentClassification


@pytest.mark.asyncio
async def test_health(client):
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"


@pytest.mark.asyncio
async def test_chat_empty_message(client):
    response = await client.post("/api/v1/chat", json={"message": ""})
    assert response.status_code == 422  # Validation error


@pytest.mark.asyncio
async def test_agent_status(client):
    response = await client.get("/api/v1/status")
    assert response.status_code == 200


def _not_severe():
    return patch(
        "src.agents.nodes.safety_guard_node.get_llm",
        **{"return_value.ainvoke": AsyncMock(return_value=AIMessage(content="KHONG"))},
    )


def _classified_general():
    return patch(
        "src.agents.nodes.classify_intent_node.get_llm",
        **{
            "return_value.with_structured_output.return_value.ainvoke": AsyncMock(
                return_value=IntentClassification(intent="general")
            )
        },
    )


def _reaches_agent():
    stack = ExitStack()
    stack.enter_context(_not_severe())
    stack.enter_context(_classified_general())
    return stack


@pytest.mark.asyncio
async def test_chat_voice_missing_fields(client):
    response = await client.post("/api/v1/chat/voice", data={})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_chat_voice_happy_path(client):
    with (
        _reaches_agent(),
        patch("src.api.routes.transcribe_audio", new=AsyncMock(return_value="tôi uống thuốc chưa nhỉ")),
        patch("src.api.routes.synthesize_speech", new=AsyncMock(return_value=b"mp3-bytes")),
        patch("src.agents.nodes.chat_node.get_llm") as mock_chat_llm,
    ):
        mock_chat_llm.return_value.bind_tools.return_value.ainvoke = AsyncMock(
            return_value=AIMessage(content="Bạn đã uống Metformin lúc 07:00 rồi nhé.")
        )
        response = await client.post(
            "/api/v1/chat/voice",
            data={"patient_id": "patient-123"},
            files={"audio": ("rec.webm", b"fake-audio-bytes", "audio/webm")},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["transcript"] == "tôi uống thuốc chưa nhỉ"
    assert body["response"] == "Bạn đã uống Metformin lúc 07:00 rồi nhé."
    assert body["audio_base64"] is not None


@pytest.mark.asyncio
async def test_chat_voice_stt_failure_returns_502(client):
    from src.services.speech import SpeechServiceError

    with patch(
        "src.api.routes.transcribe_audio",
        new=AsyncMock(side_effect=SpeechServiceError("mic hỏng")),
    ):
        response = await client.post(
            "/api/v1/chat/voice",
            data={"patient_id": "patient-123"},
            files={"audio": ("rec.webm", b"fake-audio-bytes", "audio/webm")},
        )

    assert response.status_code == 502


@pytest.mark.asyncio
async def test_chat_voice_tts_failure_still_returns_text_response(client):
    from src.services.speech import SpeechServiceError

    with (
        _reaches_agent(),
        patch("src.api.routes.transcribe_audio", new=AsyncMock(return_value="xin chào")),
        patch("src.api.routes.synthesize_speech", new=AsyncMock(side_effect=SpeechServiceError("quota"))),
        patch("src.agents.nodes.chat_node.get_llm") as mock_chat_llm,
    ):
        mock_chat_llm.return_value.bind_tools.return_value.ainvoke = AsyncMock(
            return_value=AIMessage(content="Chào bạn!")
        )
        response = await client.post(
            "/api/v1/chat/voice",
            data={"patient_id": "patient-123"},
            files={"audio": ("rec.webm", b"fake-audio-bytes", "audio/webm")},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["response"] == "Chào bạn!"
    assert body["audio_base64"] is None


@pytest.mark.asyncio
async def test_chat_voice_empty_transcript_returns_422(client):
    with patch("src.api.routes.transcribe_audio", new=AsyncMock(return_value="")):
        response = await client.post(
            "/api/v1/chat/voice",
            data={"patient_id": "patient-123"},
            files={"audio": ("rec.webm", b"fake-audio-bytes", "audio/webm")},
        )

    assert response.status_code == 422
