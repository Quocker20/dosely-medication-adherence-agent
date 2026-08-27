"""Read-through response cache built on the shared Redis client.

Separate from src/core/redis.py on purpose: that module owns the connection
singleton and the dashboard pub/sub transport, this module owns the response
cache built on top of it. Both are infrastructure (src/core/), not a domain
module, per structure.md — no vertical slice should own the caching contract
another slice also needs.
"""

import hashlib
import json
import logging
from typing import Any, Awaitable, Callable, Dict, Optional, Type, TypeVar

from pydantic import BaseModel

from src.core.config import get_settings
from src.core.redis import get_redis_client

logger = logging.getLogger(__name__)

ModelT = TypeVar("ModelT", bound=BaseModel)


def build_cache_key(
    namespace: str,
    *,
    actor: Optional[Dict[str, Any]] = None,
    params: Optional[Dict[str, Any]] = None,
) -> str:
    """Deterministic cache key for one read endpoint call.

    `actor` folds the caller's identity (sub + role) into the key. Required
    for any endpoint whose result is scoped by RBAC/ownership (a doctor's
    roster, a patient's adherence) — omitting it would let one caller's
    cached response be served to another caller who is not entitled to see
    it. Only omit `actor` for data that is identical for every caller
    regardless of who's asking (the medication catalog).
    """
    payload: Dict[str, Any] = {"params": params or {}}
    if actor is not None:
        payload["actor"] = {"sub": actor.get("sub"), "role": actor.get("role")}
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()
    prefix = get_settings().cache_key_prefix
    return f"{prefix}:{namespace}:{digest}"


async def cache_get_json(key: str) -> Optional[Any]:
    """Fail-open read: a Redis outage or a malformed entry is a cache miss,
    never a 500 — same reasoning as publish_dashboard_event in core/redis.py."""
    if not get_settings().cache_enabled:
        return None
    try:
        client = await get_redis_client()
        raw = await client.get(key)
    except Exception:  # noqa: BLE001 — cache must never fail the request it serves
        logger.warning("Cache read failed for key %s", key, exc_info=True)
        return None
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        logger.warning("Dropping malformed cache entry for key %s", key)
        return None


async def cache_set_json(key: str, value: Any, ttl_seconds: int) -> None:
    """Fail-open write: a Redis outage must not fail a request that already
    has its answer."""
    if not get_settings().cache_enabled or ttl_seconds <= 0:
        return
    try:
        client = await get_redis_client()
        await client.set(key, json.dumps(value, default=str), ex=ttl_seconds)
    except Exception:  # noqa: BLE001 — see cache_get_json
        logger.warning("Cache write failed for key %s", key, exc_info=True)


async def cached_model(
    key: str,
    ttl_seconds: int,
    model_type: Type[ModelT],
    loader: Callable[[], Awaitable[ModelT]],
) -> ModelT:
    """Read-through cache for one Pydantic response model.

    A `loader` exception (NotFoundException, ForbiddenException, ...)
    propagates uncached: caching a denial or an out-of-scope 404 would let a
    stale access decision outlive the request that produced it, on an
    endpoint whose whole point is per-caller scoping.
    """
    cached = await cache_get_json(key)
    if cached is not None:
        try:
            return model_type.model_validate(cached)
        except Exception:  # noqa: BLE001 — corrupt/stale-shape entry is a miss, not a crash
            logger.warning("Cached value failed validation for key %s", key, exc_info=True)

    result = await loader()
    await cache_set_json(key, result.model_dump(mode="json"), ttl_seconds)
    return result


async def invalidate_prefix(namespace: str) -> None:
    """Drop every cached entry whose key starts with `namespace`.

    For a write whose effect a cached read must reflect immediately (e.g. a
    dashboard roster cached under "dash:patients:list"/"dash:patients:detail"
    after an alert opens) — call this right after the transaction that wrote
    it commits, the same "after commit, fail-open" placement already used for
    publish_dashboard_event. SCAN, never KEYS: this runs against a live Redis
    instance shared with the dashboard pub/sub channel and must not block it.
    """
    if not get_settings().cache_enabled:
        return
    prefix = get_settings().cache_key_prefix
    pattern = f"{prefix}:{namespace}*"
    try:
        client = await get_redis_client()
        keys = [k async for k in client.scan_iter(match=pattern, count=200)]
        if keys:
            await client.unlink(*keys)
    except Exception:  # noqa: BLE001 — invalidation failure must not fail the write it guards
        logger.warning("Cache invalidation failed for namespace %s", namespace, exc_info=True)
