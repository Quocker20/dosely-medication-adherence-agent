"""Login brute-force lockout keyed by phone number (SEC-03).

PINs are 6 digits (a deliberate product choice), so the only defence against
guessing is limiting attempts. State lives in Redis:

* ``loginfail:{phone}``  consecutive failures, TTL = FAIL_WINDOW_SECONDS
* ``loginlock:{phone}``  present while locked, TTL = lock duration
* ``loginlevel:{phone}`` how many lockouts in the last 24 h (escalation), TTL 24 h

Lock duration escalates 15 min -> 1 h on repeats within 24 h (1 h is the cap). A
successful login clears the failure counter (not the escalation level).

Keyed by phone, not by user id, and counts unknown phones too, so the response
never reveals whether an account exists.

Fail-open like the rate limiter (P-11): a Redis outage logs a warning and lets
logins proceed rather than locking everyone out of a medication app.
"""

import logging
import math

from src.core.config import get_settings
from src.core.redis import get_redis_client

logger = logging.getLogger(__name__)

MAX_FAILURES = 5
FAIL_WINDOW_SECONDS = 15 * 60
LEVEL_WINDOW_SECONDS = 24 * 60 * 60
LOCK_DURATIONS = (15 * 60, 60 * 60)


def _fail_key(phone: str) -> str:
    return f"loginfail:{phone}"


def _lock_key(phone: str) -> str:
    return f"loginlock:{phone}"


def _level_key(phone: str) -> str:
    return f"loginlevel:{phone}"


def _enabled() -> bool:
    return get_settings().rate_limit_enabled


def lock_message(seconds: int) -> str:
    """Vietnamese, user-facing, safe to show verbatim."""
    if seconds >= 3600:
        wait = f"{math.ceil(seconds / 3600)} giờ"
    else:
        wait = f"{max(1, math.ceil(seconds / 60))} phút"
    return f"Bạn đã nhập sai quá nhiều lần. Vui lòng thử lại sau {wait}."


async def get_lock_remaining(phone: str) -> int:
    """Seconds left on an active lock, or 0."""
    if not _enabled():
        return 0
    try:
        redis = await get_redis_client()
        ttl = await redis.ttl(_lock_key(phone))
    except Exception:  # noqa: BLE001 - fail-open
        logger.warning("Login lockout check unavailable (Redis error)", exc_info=True)
        return 0
    return int(ttl) if ttl and ttl > 0 else 0


async def register_failure(phone: str) -> int:
    """Record a failed attempt. Returns the new lock duration in seconds if this
    failure triggered a lock, else 0."""
    if not _enabled():
        return 0
    try:
        redis = await get_redis_client()
        async with redis.pipeline(transaction=True) as pipe:
            pipe.set(_fail_key(phone), 0, ex=FAIL_WINDOW_SECONDS, nx=True)
            pipe.incr(_fail_key(phone))
            results = await pipe.execute()
        if int(results[-1]) < MAX_FAILURES:
            return 0
        async with redis.pipeline(transaction=True) as pipe:
            pipe.set(_level_key(phone), 0, ex=LEVEL_WINDOW_SECONDS, nx=True)
            pipe.incr(_level_key(phone))
            results = await pipe.execute()
        level = max(int(results[-1]), 1)
        duration = LOCK_DURATIONS[min(level, len(LOCK_DURATIONS)) - 1]
        async with redis.pipeline(transaction=True) as pipe:
            pipe.set(_lock_key(phone), 1, ex=duration)
            pipe.delete(_fail_key(phone))
            await pipe.execute()
        return duration
    except Exception:  # noqa: BLE001 - fail-open
        logger.warning("Login lockout counter unavailable (Redis error)", exc_info=True)
        return 0


async def reset_failures(phone: str) -> None:
    """Clear the consecutive-failure counter after a successful login."""
    if not _enabled():
        return
    try:
        redis = await get_redis_client()
        await redis.delete(_fail_key(phone))
    except Exception:  # noqa: BLE001 - fail-open
        logger.warning("Login lockout reset unavailable (Redis error)", exc_info=True)
