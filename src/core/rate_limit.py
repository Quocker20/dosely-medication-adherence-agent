from collections.abc import Callable
from typing import Any

from fastapi import Depends, Request

from src.common.exceptions import TooManyRequestsException
from src.common.http import get_client_ip
from src.core.config import get_settings
from src.core.redis import get_redis_client
from src.core.security import get_current_user_payload


async def _check(
    scope: str,
    identifier: str,
    max_requests: int,
    window_seconds: int,
) -> None:
    if not get_settings().rate_limit_enabled:
        return

    redis = await get_redis_client()
    key = f"ratelimit:{scope}:{identifier}"
    count = await redis.incr(key)
    if count == 1:
        await redis.expire(key, window_seconds)
    if count > max_requests:
        raise TooManyRequestsException(
            message=f"Quá {max_requests} yêu cầu / {window_seconds}s cho {scope}.",
            retry_after_seconds=window_seconds,
        )


def rate_limit_by_user(
    scope: str,
    max_requests: int,
    window_seconds: int,
) -> Callable[..., Any]:
    """Rate-limit authenticated routes by JWT subject."""

    async def dependency(
        current_user: dict = Depends(get_current_user_payload),
    ) -> None:
        await _check(scope, current_user["sub"], max_requests, window_seconds)

    return dependency


def rate_limit_by_ip(
    scope: str,
    max_requests: int,
    window_seconds: int,
) -> Callable[..., Any]:
    """Rate-limit unauthenticated routes by client IP."""

    async def dependency(request: Request) -> None:
        await _check(scope, get_client_ip(request), max_requests, window_seconds)

    return dependency
