import logging
from collections.abc import Callable
from typing import Any

from fastapi import Depends, Request

from src.common.exceptions import TooManyRequestsException
from src.common.http import get_client_ip
from src.core.config import get_settings
from src.core.redis import get_redis_client
from src.core.security import get_current_user_payload

logger = logging.getLogger(__name__)


async def _check(
    scope: str,
    identifier: str,
    max_requests: int,
    window_seconds: int,
) -> None:
    """Count one request; raise 429 when over the limit.

    Fail-open (P-11): if Redis errors, log a WARNING and let the request
    through rather than 500 the whole API on a cache outage.
    """
    if not get_settings().rate_limit_enabled:
        return

    key = f"ratelimit:{scope}:{identifier}"
    try:
        redis = await get_redis_client()
        # One round trip, MULTI/EXEC: SET NX EX creates the key together with
        # its TTL (no window where the key exists without an expiry), then INCR
        # counts. A crash between the two old calls could leave an immortal key.
        async with redis.pipeline(transaction=True) as pipe:
            pipe.set(key, 0, ex=window_seconds, nx=True)
            pipe.incr(key)
            results = await pipe.execute()
        count = int(results[-1])
    except Exception:  # noqa: BLE001 - fail-open, see docstring
        logger.warning(
            "Rate limiter unavailable (Redis error); allowing request. scope=%s",
            scope,
            exc_info=True,
        )
        return
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
