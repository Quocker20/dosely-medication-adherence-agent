from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from src.services.backend_client import BackendAPIError, get, post


def _mock_async_client(*, raises: Exception | None = None, response: MagicMock | None = None):
    """Patch httpx.AsyncClient so `async with AsyncClient(...) as client` yields
    a client whose .get/.post either raises or returns `response`."""
    mock_client = AsyncMock()
    if raises is not None:
        mock_client.get.side_effect = raises
        mock_client.post.side_effect = raises
    else:
        mock_client.get.return_value = response
        mock_client.post.return_value = response

    mock_ctx = MagicMock()
    mock_ctx.__aenter__.return_value = mock_client
    mock_ctx.__aexit__.return_value = False
    return patch("src.services.backend_client.httpx.AsyncClient", return_value=mock_ctx)


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
