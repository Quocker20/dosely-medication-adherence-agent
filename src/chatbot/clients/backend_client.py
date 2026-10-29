"""Async HTTP client for calling the Dosely FastAPI backend from agent tools.

Endpoints and DTOs here follow api-contract.md / schema.md at the repo root.
"""
from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

import httpx

from src.core.config import get_settings
from src.core.security import get_actor_token

logger = logging.getLogger(__name__)

# SEC-23: the only text a patient may see for a backend/connection failure.
# Raw exception text can carry hostnames, ports and response bodies.
GENERIC_BACKEND_ERROR = "Hệ thống tạm thời chưa phản hồi, bạn vui lòng thử lại sau."

_UUID = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")


def _safe_path(path: str) -> str:
    """Path for logs with identifiers removed (patient ids are PHI)."""
    return _UUID.sub("{id}", path.split("?", 1)[0])


class BackendAPIError(Exception):
    """Raised when the backend responds with an error status."""

    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"Backend API error {status_code}: {detail}")


_ENVELOPE_KEYS = {"success", "code", "message", "data"}


def _headers(extra: dict[str, str] | None = None) -> dict[str, str]:
    settings = get_settings()
    headers = {"Content-Type": "application/json"}
    # Prefer the identity of the caller whose request we are serving: the
    # backend's require_roles guards check the JWT's role AND the service layer
    # checks sub == patient_id, so calls made under the patient's own token pass
    # both without a privileged service account existing at all.
    token = get_actor_token() or settings.api_service_token
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if extra:
        headers.update(extra)
    return headers


def _unwrap(payload: Any) -> Any:
    """Strip the backend's standard response envelope.

    Every endpoint wraps its result as {success, code, message, data, errors}
    (src/core/response.py). Tools want the payload, not the envelope — without
    this, `page.get("content")` looks one level too high and silently misses.
    Non-enveloped bodies pass through unchanged.
    """
    if isinstance(payload, dict) and _ENVELOPE_KEYS <= payload.keys():
        return payload.get("data")
    return payload


def _error_detail(resp: httpx.Response) -> str:
    """Patient-safe reason from an error response.

    Errors are enveloped too, and tools splice `detail` straight into what the
    patient reads. Only the envelope's own `message` (written by the backend
    for users, e.g. validation text) is surfaced; anything else -- non-JSON
    bodies, unknown JSON shapes -- becomes the generic message (SEC-23).
    """
    try:
        body = resp.json()
    except ValueError:
        return GENERIC_BACKEND_ERROR
    if isinstance(body, dict) and isinstance(body.get("message"), str):
        return body["message"]
    return GENERIC_BACKEND_ERROR


# P-10: one shared client (connection pooling / keep-alive) per event loop.
_client: httpx.AsyncClient | None = None
_client_loop: asyncio.AbstractEventLoop | None = None


def _discard_client(
    client: httpx.AsyncClient | None, loop: asyncio.AbstractEventLoop | None
) -> None:
    """Best-effort close of a client we are replacing. Never raises.

    Its loop may already be closed (then only dropping the reference is
    possible); a still-running loop gets the aclose scheduled on it.
    """
    if client is None or client.is_closed:
        return
    try:
        if loop is not None and loop.is_running():
            if loop is asyncio.get_running_loop():
                task = loop.create_task(client.aclose())
                task.add_done_callback(lambda t: t.cancelled() or t.exception())
            else:
                asyncio.run_coroutine_threadsafe(client.aclose(), loop)
    except Exception:  # noqa: BLE001 — replacing the client must not fail a request
        logger.debug("Closing the replaced backend HTTP client failed", exc_info=True)


def _get_client() -> httpx.AsyncClient:
    global _client, _client_loop
    loop = asyncio.get_running_loop()
    if _client is None or _client.is_closed or _client_loop is not loop:
        # A client bound to another (e.g. finished) loop cannot be reused.
        _discard_client(_client, _client_loop)
        settings = get_settings()
        _client = httpx.AsyncClient(
            base_url=settings.api_base_url, timeout=settings.api_timeout_seconds
        )
        _client_loop = loop
    return _client


async def close_client() -> None:
    """Close the shared client (app shutdown). Safe to call repeatedly."""
    global _client, _client_loop
    client, _client, _client_loop = _client, None, None
    if client is not None and not client.is_closed:
        try:
            await client.aclose()
        except Exception:  # noqa: BLE001 — shutdown must not raise
            logger.warning("Closing the backend HTTP client failed", exc_info=True)


async def _request(method: str, path: str, **kwargs: Any) -> Any:
    try:
        resp = await _get_client().request(method, path, **kwargs)
    except httpx.HTTPError as e:
        # Mất kết nối/timeout — không phải lỗi HTTP status, httpx không tự
        # gói vào response. Gói thành BackendAPIError để MỌI tool gọi qua
        # get()/post() chỉ cần bắt 1 loại exception, không tự crash khi
        # backend down/mất mạng. Chi tiết (host, cổng...) chỉ ghi log.
        logger.warning(
            "Backend %s %s failed: %s", method, _safe_path(path), type(e).__name__
        )
        raise BackendAPIError(503, GENERIC_BACKEND_ERROR) from e
    if resp.is_error:
        logger.warning(
            "Backend %s %s returned %s", method, _safe_path(path), resp.status_code
        )
        raise BackendAPIError(resp.status_code, _error_detail(resp))
    return _unwrap(resp.json())


async def get(path: str, params: dict[str, Any] | None = None) -> Any:
    return await _request("GET", path, params=params, headers=_headers())


async def post(
    path: str,
    json: dict[str, Any],
    headers: dict[str, str] | None = None,
) -> Any:
    return await _request("POST", path, json=json, headers=_headers(headers))
