"""Redis working memory; PostgreSQL remains the durable source."""
from __future__ import annotations

import json
import logging
from typing import Any

from src.core.redis import get_redis_client

logger = logging.getLogger(__name__)
TTL_SECONDS = 3600


def _key(patient_id: str, conversation_id: str) -> str:
    return f"remindrx:chat:memory:{patient_id}:{conversation_id}"


async def load_working_memory(patient_id: str, conversation_id: str) -> dict[str, Any]:
    try:
        raw = await (await get_redis_client()).get(_key(patient_id, conversation_id))
        value = json.loads(raw) if raw else {}
        return value if isinstance(value, dict) else {}
    except Exception:
        logger.warning("Redis chat memory read failed", exc_info=True)
        return {}


async def save_working_memory(patient_id: str, conversation_id: str, value: dict[str, Any]) -> None:
    try:
        await (await get_redis_client()).set(
            _key(patient_id, conversation_id), json.dumps(value, ensure_ascii=False, default=str), ex=TTL_SECONDS
        )
    except Exception:
        logger.warning("Redis chat memory write failed", exc_info=True)
