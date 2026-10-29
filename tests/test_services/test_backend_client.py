from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from src.chatbot.clients.backend_client import GENERIC_BACKEND_ERROR, BackendAPIError, get, post
from src.core.security import get_actor_token, reset_actor_token, set_actor_token


def _mock_async_client(*, raises: Exception | None = None, response: MagicMock | None = None):
    """Patch the shared client getter so .request either raises or returns
    `response`."""
    mock_client = AsyncMock()
    if raises is not None:
        mock_client.request.side_effect = raises
    else:
        mock_client.request.return_value = response
    return patch("src.chatbot.clients.backend_client._get_client", return_value=mock_client)


@pytest.mark.asyncio
async def test_get_wraps_connection_error_into_backend_api_error():
    """Regression: trước đây httpx.ConnectError (backend down/mất mạng) lọt
    thẳng ra ngoài chưa được bắt, làm crash caller (vd rescheduling_node gọi
    tool trực tiếp, không qua ToolNode nên không có lưới an toàn nào khác).
    Phát hiện khi chạy eval/end_to_end_conversations_eval.py."""
    with _mock_async_client(raises=httpx.ConnectError("boom")):
        with pytest.raises(BackendAPIError) as exc_info:
            await get("/patients/p1/prescriptions")

    assert exc_info.value.status_code == 503


@pytest.mark.asyncio
async def test_post_wraps_timeout_into_backend_api_error():
    with _mock_async_client(raises=httpx.TimeoutException("timed out")):
        with pytest.raises(BackendAPIError) as exc_info:
            await post("/patients/p1/schedules/reschedule", json={"reason": "x"})

    assert exc_info.value.status_code == 503


@pytest.mark.asyncio
async def test_get_raises_backend_api_error_on_http_error_status():
    response = MagicMock(is_error=True, status_code=404, text="not found")
    with _mock_async_client(response=response):
        with pytest.raises(BackendAPIError) as exc_info:
            await get("/patients/p1/prescriptions")

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_get_returns_json_on_success():
    response = MagicMock(is_error=False)
    response.json.return_value = {"content": []}
    with _mock_async_client(response=response):
        result = await get("/patients/p1/prescriptions")

    assert result == {"content": []}


def _envelope(data):
    """Exactly what src/core/response.py:success_response puts on the wire."""
    return {"success": True, "code": 200, "message": "ok", "data": data, "errors": None}


@pytest.mark.asyncio
async def test_get_strips_response_envelope():
    """Regression: every backend endpoint wraps its result in the standard
    envelope, so `page["content"]` sat one level below where the tools looked.
    They fell back to stringifying the whole envelope instead of failing, so the
    LLM silently got {'success': True, ...} where a prescription list belonged."""
    page = {"content": [{"id": "rx-1"}], "page_no": 1, "total_elements": 1}
    response = MagicMock(is_error=False)
    response.json.return_value = _envelope(page)
    with _mock_async_client(response=response):
        result = await get("/patients/p1/prescriptions")

    assert result == page
    assert result["content"] == [{"id": "rx-1"}]


@pytest.mark.asyncio
async def test_post_strips_response_envelope():
    response = MagicMock(is_error=False)
    response.json.return_value = _envelope({"agent_run_id": "run-1", "status": "RUNNING"})
    with _mock_async_client(response=response):
        result = await post("/patients/p1/schedules/reschedule", json={"reason": "x"})

    assert result == {"agent_run_id": "run-1", "status": "RUNNING"}


@pytest.mark.asyncio
async def test_error_detail_prefers_envelope_message_over_raw_body():
    """`detail` gets spliced into the sentence a patient reads — a raw JSON
    blob there is a leak of internals as much as it is bad Vietnamese."""
    response = MagicMock(is_error=True, status_code=422, text='{"raw":"json"}')
    response.json.return_value = {
        "success": False,
        "code": 422,
        "message": "Idempotency-Key header is required",
        "data": None,
        "errors": None,
    }
    with _mock_async_client(response=response):
        with pytest.raises(BackendAPIError) as exc_info:
            await post("/patients/p1/sos", json={})

    assert exc_info.value.detail == "Idempotency-Key header is required"


@pytest.mark.asyncio
async def test_calls_carry_the_actor_token_when_one_is_bound():
    """The agent runs in-process but reaches the backend over HTTP, hitting the
    same require_roles guards as any client. Calls must travel as the patient
    whose turn is being served, not as a privileged service account."""
    mock_client = AsyncMock()
    mock_client.request.return_value = MagicMock(is_error=False, **{"json.return_value": {}})

    handle = set_actor_token("patient-jwt-abc")
    try:
        with patch(
            "src.chatbot.clients.backend_client._get_client",
            return_value=mock_client,
        ):
            await get("/patients/p1/routine")
    finally:
        reset_actor_token(handle)

    headers = mock_client.request.call_args.kwargs["headers"]
    assert headers["Authorization"] == "Bearer patient-jwt-abc"


@pytest.mark.asyncio
async def test_actor_token_does_not_leak_past_reset():
    """A token left bound would be handed to whatever runs next on this task."""
    handle = set_actor_token("patient-jwt-abc")
    reset_actor_token(handle)
    assert get_actor_token() is None


@pytest.mark.asyncio
async def test_shared_client_is_reused_and_closed():
    """P-10: one AsyncClient serves every call on a loop; close_client()
    shuts it and the next call lazily builds a fresh one."""
    from src.chatbot.clients import backend_client

    await backend_client.close_client()
    first = backend_client._get_client()
    assert backend_client._get_client() is first
    await backend_client.close_client()
    assert first.is_closed
    second = backend_client._get_client()
    assert second is not first
    await backend_client.close_client()


@pytest.mark.asyncio
async def test_per_request_headers_still_apply_with_shared_client():
    mock_client = AsyncMock()
    mock_client.request.return_value = MagicMock(is_error=False, **{"json.return_value": {}})
    with patch("src.chatbot.clients.backend_client._get_client", return_value=mock_client):
        await post("/x", json={"a": 1}, headers={"Idempotency-Key": "k1"})
    kwargs = mock_client.request.call_args.kwargs
    assert kwargs["headers"]["Idempotency-Key"] == "k1"
    assert kwargs["headers"]["Content-Type"] == "application/json"
    assert kwargs["json"] == {"a": 1}


@pytest.mark.asyncio
async def test_connection_error_gives_generic_message_without_host():
    """SEC-23: no hostnames/ports/exception text reach the patient."""
    exc = httpx.ConnectError("All connection attempts failed to db-internal.corp:8123")
    with _mock_async_client(raises=exc):
        with pytest.raises(BackendAPIError) as ei:
            await get("/patients/p1/routine")
    assert ei.value.status_code == 503
    assert ei.value.detail == GENERIC_BACKEND_ERROR
    assert "db-internal" not in ei.value.detail
    assert "8123" not in str(ei.value)


@pytest.mark.asyncio
async def test_non_json_error_body_gives_generic_message():
    resp = MagicMock(is_error=True, status_code=502, text="<html>upstream 10.0.0.5 traceback</html>")
    resp.json.side_effect = ValueError("not json")
    with _mock_async_client(response=resp):
        with pytest.raises(BackendAPIError) as ei:
            await get("/x")
    assert ei.value.detail == GENERIC_BACKEND_ERROR
    assert "10.0.0.5" not in str(ei.value)


@pytest.mark.asyncio
async def test_enveloped_error_message_still_surfaces():
    resp = MagicMock(is_error=True, status_code=422)
    resp.json.return_value = {"success": False, "code": 422, "message": "Liều không hợp lệ"}
    with _mock_async_client(response=resp):
        with pytest.raises(BackendAPIError) as ei:
            await post("/x", json={})
    assert ei.value.detail == "Liều không hợp lệ"


@pytest.mark.asyncio
async def test_voice_transcription_failure_returns_generic_message():
    from src.chatbot.clients.speech import SpeechServiceError
    from src.common.exceptions import AppException
    from src.modules.agents.chat_service import ChatService

    err = SpeechServiceError("Không nhận dạng được giọng nói: 401 key sk-secret at api.openai.com")
    with patch("src.modules.agents.chat_service.transcribe_audio", AsyncMock(side_effect=err)):
        with pytest.raises(AppException) as ei:
            await ChatService().handle_voice_chat(b"x", "a.wav", "p1")
    assert ei.value.code == 502
    assert ei.value.message == GENERIC_BACKEND_ERROR
    assert "sk-secret" not in ei.value.message and "openai" not in ei.value.message


def test_new_event_loop_gets_new_client_and_closes_old_one():
    """The client bound to a finished loop is replaced (best-effort close),
    without raising or leaking a ResourceWarning."""
    import asyncio
    import warnings

    from src.chatbot.clients import backend_client as bc

    closed: list[httpx.AsyncClient] = []

    async def first():
        return bc._get_client()

    async def second():
        return bc._get_client()

    with warnings.catch_warnings():
        warnings.simplefilter("error", ResourceWarning)
        c1 = asyncio.run(first())
        orig = httpx.AsyncClient.aclose

        async def spy(self):
            closed.append(self)
            await orig(self)

        httpx.AsyncClient.aclose = spy
        try:
            c2 = asyncio.run(second())
        finally:
            httpx.AsyncClient.aclose = orig
        assert c2 is not c1
        assert closed == []  # old loop is closed: reference dropped, no error
        bc._client, bc._client_loop = None, None
