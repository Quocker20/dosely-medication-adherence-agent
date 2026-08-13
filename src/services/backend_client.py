"""Async HTTP client for calling the RemindRx FastAPI backend from agent tools.

Endpoints and DTOs here follow api-contract.md / schema.md at the repo root.
"""
from __future__ import annotations

from typing import Any

import httpx

from src.config import get_settings


class BackendAPIError(Exception):
    """Raised when the backend responds with an error status."""

    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"Backend API error {status_code}: {detail}")


def _headers(extra: dict[str, str] | None = None) -> dict[str, str]:
    settings = get_settings()
    headers = {"Content-Type": "application/json"}
    if settings.api_service_token:
        headers["Authorization"] = f"Bearer {settings.api_service_token}"
    if extra:
        headers.update(extra)
    return headers


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
        raise BackendAPIError(resp.status_code, resp.text)
    return resp.json()


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
        raise BackendAPIError(resp.status_code, resp.text)
    return resp.json()
