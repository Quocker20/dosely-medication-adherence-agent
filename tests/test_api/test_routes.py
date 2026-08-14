"""Chat endpoint contract: authentication, identity, and response envelope.

Both endpoints used to be unauthenticated and took `patient_id` straight from
the request. Since the agent's tools write dose actions and raise alerts, that
was a write path into any patient's record for any caller — these tests pin the
endpoints to the authenticated caller's own `sub`.
"""
from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.messages import AIMessage

from src.core.security import create_access_token
from src.modules.planning.core.speech import SpeechServiceError

PATIENT_ID = "11111111-1111-1111-1111-111111111111"
OTHER_PATIENT_ID = "22222222-2222-2222-2222-222222222222"
DOCTOR_ID = "33333333-3333-3333-3333-333333333333"


def _auth(user_id: str, role: str) -> dict[str, str]:
    token = create_access_token(user_id=user_id, role=role, phone_number="+84900000001")
    return {"Authorization": f"Bearer {token}"}


def _patient_headers() -> dict[str, str]:
    return _auth(PATIENT_ID, "PATIENT")


def _agent_replying(text: str, intent: str = "general") -> AsyncMock:
    """Stand in for the compiled LangGraph agent. The graph itself is covered by
    tests/test_agents/; here only the endpoint's contract is under test."""
    return AsyncMock(
        return_value={"messages": [AIMessage(content=text)], "intent": intent, "escalated": False}
    )


def _audio_file() -> dict:
    return {"audio": ("rec.webm", b"fake-audio-bytes", "audio/webm")}


@pytest.mark.asyncio
async def test_health(client):
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"


# ---------------------------------------------------------------------------
# POST /chat
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_chat_without_token_is_rejected(client):
    response = await client.post("/api/v1/chat", json={"message": "xin chào"})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_chat_rejects_non_patient_role(client):
    response = await client.post(
        "/api/v1/chat", json={"message": "xin chào"}, headers=_auth(DOCTOR_ID, "DOCTOR")
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_chat_empty_message(client):
    response = await client.post(
        "/api/v1/chat", json={"message": ""}, headers=_patient_headers()
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_chat_returns_reply_in_standard_envelope(client):
    """Every other endpoint wraps its result; /chat used to return the bare
    model, forcing clients to special-case it."""
    with patch("src.modules.agents.service.agent") as mock_agent:
        mock_agent.ainvoke = _agent_replying("Bạn đã uống Metformin lúc 07:00 rồi nhé.")
        response = await client.post(
            "/api/v1/chat",
            json={"message": "tôi uống thuốc chưa nhỉ"},
            headers=_patient_headers(),
        )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["code"] == 200
    assert body["errors"] is None
    assert body["data"]["response"] == "Bạn đã uống Metformin lúc 07:00 rồi nhé."


@pytest.mark.asyncio
async def test_chat_uses_token_subject_as_patient_id(client):
    with patch("src.modules.agents.service.agent") as mock_agent:
        mock_agent.ainvoke = _agent_replying("ok")
        await client.post(
            "/api/v1/chat", json={"message": "xin chào"}, headers=_patient_headers()
        )

    state = mock_agent.ainvoke.call_args.args[0]
    assert state["patient_id"] == PATIENT_ID


@pytest.mark.asyncio
async def test_chat_ignores_patient_id_supplied_in_the_body(client):
    """The old contract read patient_id from the body — a caller could converse,
    and write, as somebody else. The field is gone; sending it changes nothing."""
    with patch("src.modules.agents.service.agent") as mock_agent:
        mock_agent.ainvoke = _agent_replying("ok")
        response = await client.post(
            "/api/v1/chat",
            json={"message": "xin chào", "patient_id": OTHER_PATIENT_ID},
            headers=_patient_headers(),
        )

    assert response.status_code == 200
    state = mock_agent.ainvoke.call_args.args[0]
    assert state["patient_id"] == PATIENT_ID


@pytest.mark.asyncio
async def test_chat_binds_caller_token_for_the_agents_own_backend_calls(client):
    """The agent's tools call the backend over HTTP and hit the same RBAC
    guards. The turn must run with the caller's token bound, or every tool call
    comes back 401."""
    seen: dict[str, str | None] = {}

    async def _capture(_state):
        from src.core.security import get_actor_token

        seen["token"] = get_actor_token()
        return {"messages": [AIMessage(content="ok")], "intent": "general", "escalated": False}

    with patch("src.modules.agents.service.agent") as mock_agent:
        mock_agent.ainvoke = AsyncMock(side_effect=_capture)
        await client.post(
            "/api/v1/chat", json={"message": "xin chào"}, headers=_patient_headers()
        )

    assert seen["token"] is not None

    from src.core.security import decode_token, get_actor_token

    assert decode_token(seen["token"])["sub"] == PATIENT_ID
    # Unbound again once the request is over.
    assert get_actor_token() is None


# ---------------------------------------------------------------------------
# POST /chat/voice
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_chat_voice_without_token_is_rejected(client):
    response = await client.post("/api/v1/chat/voice", files=_audio_file())
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_chat_voice_rejects_non_patient_role(client):
    response = await client.post(
        "/api/v1/chat/voice", files=_audio_file(), headers=_auth(DOCTOR_ID, "DOCTOR")
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_chat_voice_missing_audio(client):
    response = await client.post("/api/v1/chat/voice", data={}, headers=_patient_headers())
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_chat_voice_happy_path(client):
    with (
        patch(
            "src.modules.agents.service.transcribe_audio",
            new=AsyncMock(return_value="tôi uống thuốc chưa nhỉ"),
        ),
        patch(
            "src.modules.agents.service.synthesize_speech",
            new=AsyncMock(return_value=b"mp3-bytes"),
        ),
        patch("src.modules.agents.service.agent") as mock_agent,
    ):
        mock_agent.ainvoke = _agent_replying("Bạn đã uống Metformin lúc 07:00 rồi nhé.")
        response = await client.post(
            "/api/v1/chat/voice", files=_audio_file(), headers=_patient_headers()
        )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["transcript"] == "tôi uống thuốc chưa nhỉ"
    assert data["response"] == "Bạn đã uống Metformin lúc 07:00 rồi nhé."
    assert data["audio_base64"] is not None


@pytest.mark.asyncio
async def test_chat_voice_uses_token_subject_as_patient_id(client):
    with (
        patch(
            "src.modules.agents.service.transcribe_audio", new=AsyncMock(return_value="xin chào")
        ),
        patch(
            "src.modules.agents.service.synthesize_speech", new=AsyncMock(return_value=b"mp3")
        ),
        patch("src.modules.agents.service.agent") as mock_agent,
    ):
        mock_agent.ainvoke = _agent_replying("ok")
        await client.post(
            "/api/v1/chat/voice", files=_audio_file(), headers=_patient_headers()
        )

    state = mock_agent.ainvoke.call_args.args[0]
    assert state["patient_id"] == PATIENT_ID


@pytest.mark.asyncio
async def test_chat_voice_stt_failure_returns_502(client):
    with patch(
        "src.modules.agents.service.transcribe_audio",
        new=AsyncMock(side_effect=SpeechServiceError("mic hỏng")),
    ):
        response = await client.post(
            "/api/v1/chat/voice", files=_audio_file(), headers=_patient_headers()
        )

    assert response.status_code == 502
    assert response.json()["success"] is False


@pytest.mark.asyncio
async def test_chat_voice_empty_transcript_returns_422(client):
    with patch("src.modules.agents.service.transcribe_audio", new=AsyncMock(return_value="")):
        response = await client.post(
            "/api/v1/chat/voice", files=_audio_file(), headers=_patient_headers()
        )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_chat_voice_tts_failure_still_returns_text_response(client):
    """fail-open: a broken TTS vendor must not cost the patient the answer."""
    with (
        patch(
            "src.modules.agents.service.transcribe_audio", new=AsyncMock(return_value="xin chào")
        ),
        patch(
            "src.modules.agents.service.synthesize_speech",
            new=AsyncMock(side_effect=SpeechServiceError("quota")),
        ),
        patch("src.modules.agents.service.agent") as mock_agent,
    ):
        mock_agent.ainvoke = _agent_replying("Chào bạn!")
        response = await client.post(
            "/api/v1/chat/voice", files=_audio_file(), headers=_patient_headers()
        )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["response"] == "Chào bạn!"
    assert data["audio_base64"] is None
