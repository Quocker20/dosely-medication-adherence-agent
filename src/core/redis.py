from typing import Optional
import redis.asyncio as aioredis
from src.core.config import get_settings

settings = get_settings()

redis_client: Optional[aioredis.Redis] = None


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
