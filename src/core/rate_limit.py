import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta, timezone
from typing import Any

from fastapi import Depends, Request

from src.common.exceptions import TooManyRequestsException
from src.common.http import get_client_ip
from src.core.config import get_settings
from src.core.redis import get_redis_client
from src.core.security import get_current_user_payload

logger = logging.getLogger(__name__)

# Asia/Ho_Chi_Minh is UTC+7 all year (no DST), so a fixed offset is exact and
# avoids depending on tzdata being installed (Windows dev machines).
VN_TZ = timezone(timedelta(hours=7))


def _now_utc() -> datetime:
    return datetime.now(UTC)


def vn_day_key(now: datetime | None = None) -> str:
    """Calendar day (YYYY-MM-DD) in Asia/Ho_Chi_Minh."""
    return (now or _now_utc()).astimezone(VN_TZ).strftime("%Y-%m-%d")


def seconds_until_vn_midnight(now: datetime | None = None) -> int:
    """Seconds until the next 00:00 in Asia/Ho_Chi_Minh (1..86400)."""
    local = (now or _now_utc()).astimezone(VN_TZ)
    midnight = (local + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return max(1, int((midnight - local).total_seconds()))


async def _check(
    scope: str,
    identifier: str,
    max_requests: int,
    window_seconds: int,
    message: str | None = None,
    key_suffix: str = "",
) -> None:
    """Count one request; raise 429 when over the limit.

    Fail-open (P-11): if Redis errors, log a WARNING and let the request
    through rather than 500 the whole API on a cache outage.
    """
    if not get_settings().rate_limit_enabled:
        return

    key = f"ratelimit:{scope}:{identifier}{key_suffix}"
    try:
        redis = await get_redis_client()
        # One round trip, MULTI/EXEC: SET NX EX creates the key together with
        # its TTL (no window where the key exists without an expiry), then INCR
        # counts. A crash between the two old calls could leave an immortal key.
        async with redis.pipeline(transaction=True) as pipe:
            pipe.set(key, 0, ex=window_seconds, nx=True)
            pipe.incr(key)
            pipe.ttl(key)
            results = await pipe.execute()
        count = int(results[-2])
        ttl = int(results[-1])
    except Exception:  # noqa: BLE001 - fail-open, see docstring
        logger.warning(
            "Rate limiter unavailable (Redis error); allowing request. scope=%s",
            scope,
            exc_info=True,
        )
        return
    if count > max_requests:
        # Remaining time of the window, so the client waits exactly as long as
        # needed (falls back to the full window if Redis reports no TTL).
        retry_after = ttl if 0 < ttl <= window_seconds else window_seconds
        raise TooManyRequestsException(
            message=message
            or f"Quá {max_requests} yêu cầu / {window_seconds}s cho {scope}.",
            retry_after_seconds=retry_after,
        )


def rate_limit_by_user(
    scope: str,
    max_requests: int | Callable[[], int],
    window_seconds: int,
    message: str | None = None,
) -> Callable[..., Any]:
    """Rate-limit authenticated routes by JWT subject.

    ``max_requests`` may be a zero-arg callable so a setting is read per
    request rather than frozen at import time. ``message`` overrides the 429
    text (use it for text the client shows verbatim).
    """

    async def dependency(
        current_user: dict = Depends(get_current_user_payload),
    ) -> None:
        limit = max_requests() if callable(max_requests) else max_requests
        await _check(scope, current_user["sub"], limit, window_seconds, message)

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


def rate_limit_by_user_per_vn_day(
    scope: str,
    max_requests: int | Callable[[], int],
    message: str | None = None,
) -> Callable[..., Any]:
    """Per-user limit that resets at midnight Asia/Ho_Chi_Minh (calendar day).

    The counter key carries the VN date and expires at the next VN midnight, so
    ``retry_after_seconds`` is the time until the quota comes back.
    """

    async def dependency(
        current_user: dict = Depends(get_current_user_payload),
    ) -> None:
        now = _now_utc()
        limit = max_requests() if callable(max_requests) else max_requests
        await _check(
            scope,
            current_user["sub"],
            limit,
            seconds_until_vn_midnight(now),
            message,
            key_suffix=f":{vn_day_key(now)}",
        )

    return dependency
