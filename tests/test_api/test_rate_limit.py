import uuid
from unittest.mock import AsyncMock, patch

import pytest

from src.common.exceptions import UnauthorizedException
from src.core.config import get_settings
from src.core.security import create_access_token
from src.modules.agents.schemas import ChatResponse


class FakeRedis:
    def __init__(self) -> None:
        self.counts: dict[str, int] = {}
        self.expires: dict[str, int] = {}

    async def incr(self, key: str) -> int:
        self.counts[key] = self.counts.get(key, 0) + 1
        return self.counts[key]

    async def expire(self, key: str, seconds: int) -> bool:
        self.expires[key] = seconds
        return True


@pytest.mark.asyncio
async def test_login_rate_limit_counts_by_ip(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "rate_limit_enabled", True)
    redis = FakeRedis()

    login = AsyncMock(side_effect=UnauthorizedException(message="Invalid phone number or password"))
    with (
        patch("src.core.rate_limit.get_redis_client", new=AsyncMock(return_value=redis)),
        patch("src.modules.auth.service.AuthService.login", new=login),
    ):
        for _ in range(5):
            response = await client.post(
                "/api/v1/auth/login",
                json={"phone": "+84900111222", "password": "000000"},
                headers={"X-Forwarded-For": "203.0.113.10, 10.0.0.2"},
            )
            assert response.status_code == 401

        response = await client.post(
            "/api/v1/auth/login",
            json={"phone": "+84900111222", "password": "000000"},
            headers={"X-Forwarded-For": "203.0.113.10, 10.0.0.2"},
        )

    assert response.status_code == 429
    body = response.json()
    assert body["success"] is False
    assert body["errors"] == {"retry_after_seconds": 60}
    assert redis.counts == {"ratelimit:login:203.0.113.10": 6}
    assert redis.expires == {"ratelimit:login:203.0.113.10": 60}
    assert login.await_count == 5


@pytest.mark.asyncio
async def test_chat_rate_limit_counts_by_user(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "rate_limit_enabled", True)
    redis = FakeRedis()
    user_id = str(uuid.uuid4())
    token = create_access_token(
        user_id=user_id,
        role="PATIENT",
        phone_number="+84900999888",
    )
    headers = {"Authorization": f"Bearer {token}"}
    reply = ChatResponse(response="Đã kiểm tra lịch thuốc.")

    with (
        patch("src.core.rate_limit.get_redis_client", new=AsyncMock(return_value=redis)),
        patch(
            "src.modules.agents.service.ChatService.handle_text_chat",
            new=AsyncMock(return_value=reply),
        ),
    ):
        for _ in range(20):
            response = await client.post(
                "/api/v1/chat",
                json={"message": "Lịch thuốc hôm nay?"},
                headers=headers,
            )
            assert response.status_code == 200

        response = await client.post(
            "/api/v1/chat",
            json={"message": "Lịch thuốc hôm nay?"},
            headers=headers,
        )

    assert response.status_code == 429
    assert response.json()["errors"] == {"retry_after_seconds": 60}
    assert redis.counts == {f"ratelimit:chat:{user_id}": 21}
