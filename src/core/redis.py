import json
import logging
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Dict, Optional

import redis.asyncio as aioredis

from src.core.config import get_settings

logger = logging.getLogger(__name__)

settings = get_settings()

redis_client: Optional[aioredis.Redis] = None

# Fan-out channel for the doctor dashboard's live feed. Redis pub/sub (not a
# stream) because the dashboard only ever wants what is happening now: a portal
# opened after an alert fired catches up from GET /dashboard/patients, so there
# is nothing to gain from replaying a backlog into it.
DASHBOARD_EVENTS_CHANNEL = "dashboard:events"


async def get_redis_client() -> aioredis.Redis:
    """Retrieve or initialize async Redis client connection."""
    global redis_client
    if redis_client is None:
        redis_client = aioredis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
        )
    return redis_client


async def close_redis_connection() -> None:
    """Close active Redis connection pool on app shutdown."""
    global redis_client
    if redis_client is not None:
        await redis_client.close()
        redis_client = None


async def publish_dashboard_event(event_type: str, data: Dict[str, Any]) -> None:
    """Publish one dashboard frame, swallowing any transport failure.

    The frame envelope (event_type/timestamp/data) is built here rather than by
    each caller, for the same reason core/response.py owns the HTTP envelope:
    it is transport shape, and publishers live in other slices that must not
    have to import the dashboard module to emit one event. The dashboard side
    validates what comes back out against WebSocketEventStream.

    Deliberately fail-open. Callers are clinical writes — raising an alert,
    logging a dose — whose transaction has already committed by the time they
    get here. A Redis outage must degrade the dashboard's liveness, never turn
    a committed safety alert into a 500 the caller would read as failure and
    retry.
    """
    payload = {
        "event_type": event_type,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "data": data,
    }
    try:
        client = await get_redis_client()
        await client.publish(DASHBOARD_EVENTS_CHANNEL, json.dumps(payload, default=str))
    except Exception:  # noqa: BLE001 — see docstring: liveness, not correctness
        logger.warning("Could not publish dashboard event", exc_info=True)


async def subscribe_dashboard_events() -> AsyncIterator[Dict[str, Any]]:
    """Yield dashboard frames as they arrive, until the consumer stops iterating.

    Each subscriber gets its own pubsub handle off the shared pool, so one
    disconnecting client cannot tear down another's feed. Malformed frames are
    dropped rather than raised: a single bad publish should not end a socket
    that is otherwise healthy.
    """
    client = await get_redis_client()
    pubsub = client.pubsub(ignore_subscribe_messages=True)
    await pubsub.subscribe(DASHBOARD_EVENTS_CHANNEL)
    try:
        async for message in pubsub.listen():
            if message is None or message.get("type") != "message":
                continue
            try:
                yield json.loads(message["data"])
            except (TypeError, ValueError):
                logger.warning("Dropping malformed dashboard event frame")
    finally:
        await pubsub.unsubscribe(DASHBOARD_EVENTS_CHANNEL)
        await pubsub.aclose()
