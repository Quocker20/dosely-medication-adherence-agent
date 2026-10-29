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
import time
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

from pydantic import BaseModel

from src.core.config import get_settings
from src.core.redis import get_redis_client

logger = logging.getLogger(__name__)

ModelT = TypeVar("ModelT", bound=BaseModel)


def build_cache_key(
    namespace: str,
    *,
    actor: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
) -> str:
    """Deterministic cache key for one read endpoint call.

    `actor` folds the caller's identity (sub + role) into the key. Required
    for any endpoint whose result is scoped by RBAC/ownership (a doctor's
    roster, a patient's adherence) — omitting it would let one caller's
    cached response be served to another caller who is not entitled to see
    it. Only omit `actor` for data that is identical for every caller
    regardless of who's asking (the medication catalog).
    """
    payload: dict[str, Any] = {"params": params or {}}
    if actor is not None:
        payload["actor"] = {"sub": actor.get("sub"), "role": actor.get("role")}
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()
    prefix = get_settings().cache_key_prefix
    return f"{prefix}:{namespace}:{digest}"


# Version counters outlive every entry they version (longest cache TTL is
# 86400s), so a counter can only expire after all entries written under older
# versions are already gone.
_VERSION_TTL_SECONDS = 2 * 86400


def _namespace_and_digest(key: str) -> tuple[str, str] | None:
    """Split a key built by build_cache_key; None for any other key shape."""
    head = f"{get_settings().cache_key_prefix}:"
    if not key.startswith(head):
        return None
    namespace, sep, digest = key[len(head):].rpartition(":")
    if not sep or not namespace:
        return None
    return namespace, digest


def _ancestor_prefixes(namespace: str) -> list[str]:
    """"dash:patients:list" -> ["dash", "dash:patients", "dash:patients:list"]."""
    parts = namespace.split(":")
    return [":".join(parts[: i + 1]) for i in range(len(parts))]


def _version_key(prefix_ns: str) -> str:
    return f"{get_settings().cache_key_prefix}:ver:{prefix_ns}"


async def _resolve_key(client: Any, key: str) -> str:
    """P-07: fold the current version of every namespace prefix into the key.

    invalidate_prefix() bumps a counter instead of SCAN+UNLINK-ing the shared
    keyspace; entries written under the old version simply become unreachable
    and expire by TTL. Keys not built by build_cache_key pass through as-is.
    """
    parsed = _namespace_and_digest(key)
    if parsed is None:
        return key
    namespace, digest = parsed
    prefixes = _ancestor_prefixes(namespace)
    versions = await client.mget([_version_key(p) for p in prefixes])
    tag = ".".join(
        (v.decode() if isinstance(v, bytes) else str(v)) if v is not None else "0"
        for v in versions
    )
    return f"{get_settings().cache_key_prefix}:{namespace}:v{tag}:{digest}"


async def cache_get_json(key: str) -> Any | None:
    """Fail-open read: a Redis outage or a malformed entry is a cache miss,
    never a 500 — same reasoning as publish_dashboard_event in core/redis.py."""
    if not get_settings().cache_enabled:
        return None
    try:
        client = await get_redis_client()
        raw = await client.get(await _resolve_key(client, key))
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
        await client.set(
            await _resolve_key(client, key), json.dumps(value, default=str), ex=ttl_seconds
        )
    except Exception:  # noqa: BLE001 — see cache_get_json
        logger.warning("Cache write failed for key %s", key, exc_info=True)


async def cached_model(
    key: str,
    ttl_seconds: int,
    model_type: type[ModelT],
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
    """Drop every cached entry whose namespace starts with `namespace`.

    `namespace` must be a ":"-boundary prefix of the namespaces passed to
    build_cache_key ("dash:patients" covers "dash:patients:list" and
    "dash:patients:detail"). For a write whose effect a cached read must
    reflect immediately -- call this right after the transaction that wrote it
    commits, the same "after commit, fail-open" placement used for
    publish_dashboard_event.

    P-07: O(1) version bump, no SCAN over the shared Redis keyspace. The new
    version is a nanosecond timestamp so it can never repeat a value an older
    entry was written under, even if the counter key was evicted.
    """
    if not get_settings().cache_enabled:
        return
    try:
        client = await get_redis_client()
        await client.set(
            _version_key(namespace), str(time.time_ns()), ex=_VERSION_TTL_SECONDS
        )
    except Exception:  # noqa: BLE001 — invalidation failure must not fail the write it guards
        logger.warning("Cache invalidation failed for namespace %s", namespace, exc_info=True)
