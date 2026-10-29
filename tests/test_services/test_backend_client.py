from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from src.chatbot.clients.backend_client import BackendAPIError, get, post
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
