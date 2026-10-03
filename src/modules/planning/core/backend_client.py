"""Async HTTP client for calling the Dosely FastAPI backend from agent tools.

Endpoints and DTOs here follow api-contract.md / schema.md at the repo root.
"""
from __future__ import annotations

from typing import Any

import httpx

from src.core.config import get_settings
from src.core.security import get_actor_token


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
    """Human-readable reason from an error response.

    Errors are enveloped too, and tools splice `detail` straight into what the
    patient reads — surfacing `message` keeps a raw JSON blob out of the reply.
    """
    try:
        body = resp.json()
    except ValueError:
        return resp.text
    if isinstance(body, dict) and isinstance(body.get("message"), str):
        return body["message"]
    return resp.text


async def get(path: str, params: dict[str, Any] | None = None) -> Any:
    settings = get_settings()
    try:
        async with httpx.AsyncClient(
            base_url=settings.api_base_url, timeout=settings.api_timeout_seconds
        ) as client:
            resp = await client.get(path, params=params, headers=_headers())
    except httpx.HTTPError as e:
        # Mất kết nối/timeout — không phải lỗi HTTP status, httpx không tự
        # gói vào response. Gói thành BackendAPIError để MỌI tool gọi qua
        # get()/post() chỉ cần bắt 1 loại exception (đã làm sẵn ở từng
        # tool), không tự crash khi backend down/mất mạng.
        raise BackendAPIError(503, f"Không kết nối được tới backend: {e}") from e
    if resp.is_error:
        raise BackendAPIError(resp.status_code, _error_detail(resp))
    return _unwrap(resp.json())


async def post(
    path: str,
    json: dict[str, Any],
    headers: dict[str, str] | None = None,
) -> Any:
    settings = get_settings()
    try:
        async with httpx.AsyncClient(
            base_url=settings.api_base_url, timeout=settings.api_timeout_seconds
        ) as client:
            resp = await client.post(path, json=json, headers=_headers(headers))
    except httpx.HTTPError as e:
        raise BackendAPIError(503, f"Không kết nối được tới backend: {e}") from e
    if resp.is_error:
        raise BackendAPIError(resp.status_code, _error_detail(resp))
    return _unwrap(resp.json())
