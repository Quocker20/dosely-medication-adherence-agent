import uuid
from unittest.mock import AsyncMock, patch

import pytest

from src.common.exceptions import UnauthorizedException
from src.core.config import get_settings
from src.core.security import create_access_token
from src.modules.agents.schemas import ChatResponse


class FakePipeline:
    def __init__(self, redis: "FakeRedis") -> None:
        self._redis = redis
        self._ops: list = []

    def set(self, key, value, ex=None, nx=False):
        self._ops.append(("set", key, value, ex, nx))
        return self

    def incr(self, key):
        self._ops.append(("incr", key))
        return self

    def ttl(self, key):
        self._ops.append(("ttl", key))
        return self

    async def execute(self):
        self._redis.round_trips += 1
        results = []
        for op in self._ops:
            if op[0] == "set":
                _, key, value, ex, nx = op
                if nx and key in self._redis.counts:
                    results.append(None)
                    continue
                self._redis.counts[key] = value
                if ex is not None:
                    self._redis.expires[key] = ex
                results.append(True)
            elif op[0] == "ttl":
                results.append(self._redis.expires.get(op[1], -1))
            else:
                self._redis.counts[op[1]] = self._redis.counts.get(op[1], 0) + 1
                results.append(self._redis.counts[op[1]])
        return results

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class FakeRedis:
    def __init__(self) -> None:
        self.counts: dict[str, int] = {}
        self.expires: dict[str, int] = {}
        self.round_trips = 0

    def pipeline(self, transaction: bool = True) -> FakePipeline:
        return FakePipeline(self)


class BrokenRedis:
    def pipeline(self, transaction: bool = True):
        raise ConnectionError("redis down")


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
                headers={"X-Forwarded-For": "198.51.100.7, 10.0.0.2"},
            )
            assert response.status_code == 401

        response = await client.post(
            "/api/v1/auth/login",
            json={"phone": "+84900111222", "password": "000000"},
            headers={"X-Forwarded-For": "198.51.100.7, 10.0.0.2"},
        )

    assert response.status_code == 429
    body = response.json()
    assert body["success"] is False
    assert body["errors"] == {"retry_after_seconds": 60}
    assert redis.counts == {"ratelimit:login:127.0.0.1": 6}
    assert redis.expires == {"ratelimit:login:127.0.0.1": 60}
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
            "src.modules.agents.chat_service.ChatService.handle_text_chat",
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
    # The 21st request is rejected by the minute limit before the daily counter
    # (dependency order), so the daily counter only saw the 20 allowed ones.
    assert redis.counts == {
        f"ratelimit:chat:{user_id}": 21,
        f"ratelimit:chat_daily:{user_id}": 20,
    }


@pytest.mark.asyncio
async def test_rate_limit_is_single_round_trip(monkeypatch):
    from src.core.rate_limit import _check

    monkeypatch.setattr(get_settings(), "rate_limit_enabled", True)
    redis = FakeRedis()
    with patch("src.core.rate_limit.get_redis_client", new=AsyncMock(return_value=redis)):
        await _check("scope", "id", 5, 60)
    assert redis.round_trips == 1
    assert redis.expires == {"ratelimit:scope:id": 60}


@pytest.mark.asyncio
async def test_rate_limit_fails_open_when_redis_errors(monkeypatch, caplog):
    from src.core.rate_limit import _check

    monkeypatch.setattr(get_settings(), "rate_limit_enabled", True)
    with (
        patch("src.core.rate_limit.get_redis_client", new=AsyncMock(return_value=BrokenRedis())),
        caplog.at_level("WARNING"),
    ):
        await _check("scope", "id", 1, 60)  # must not raise
    assert any(r.levelname == "WARNING" for r in caplog.records)


@pytest.mark.asyncio
async def test_rate_limit_fails_open_when_client_cannot_connect(monkeypatch):
    from src.core.rate_limit import _check

    monkeypatch.setattr(get_settings(), "rate_limit_enabled", True)
    with patch(
        "src.core.rate_limit.get_redis_client",
        new=AsyncMock(side_effect=ConnectionError("down")),
    ):
        await _check("scope", "id", 1, 60)


def test_get_client_ip_ignores_spoofed_x_forwarded_for():
    from starlette.requests import Request

    from src.common.http import get_client_ip

    def make(headers, client=("172.18.0.5", 5000)):
        return Request(
            {
                "type": "http",
                "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
                "client": client,
            }
        )

    assert get_client_ip(make({"X-Forwarded-For": "1.2.3.4"})) == "172.18.0.5"
    assert get_client_ip(make({})) == "172.18.0.5"
    assert get_client_ip(make({}, client=None)) == "127.0.0.1"


@pytest.mark.asyncio
async def test_chat_daily_limit_applies_to_text_and_voice_with_friendly_429(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "rate_limit_enabled", True)
    monkeypatch.setattr(get_settings(), "chat_daily_limit", 3)
    redis = FakeRedis()
    user_id = str(uuid.uuid4())
    token = create_access_token(user_id=user_id, role="PATIENT", phone_number="+84900999888")
    headers = {"Authorization": f"Bearer {token}"}
    reply = ChatResponse(response="ok")

    with (
        patch("src.core.rate_limit.get_redis_client", new=AsyncMock(return_value=redis)),
        patch(
            "src.modules.agents.chat_service.ChatService.handle_text_chat",
            new=AsyncMock(return_value=reply),
        ),
        patch(
            "src.modules.agents.chat_service.ChatService.handle_voice_chat",
            new=AsyncMock(return_value=reply),
        ),
    ):
        for _ in range(2):
            r = await client.post("/api/v1/chat", json={"message": "hi"}, headers=headers)
            assert r.status_code == 200
        voice = await client.post(
            "/api/v1/chat/voice",
            files={"audio": ("a.webm", b"x", "audio/webm")},
            headers=headers,
        )
        assert voice.status_code == 200
        blocked = await client.post("/api/v1/chat", json={"message": "hi"}, headers=headers)
        blocked_voice = await client.post(
            "/api/v1/chat/voice",
            files={"audio": ("a.webm", b"x", "audio/webm")},
            headers=headers,
        )

    for resp in (blocked, blocked_voice):
        assert resp.status_code == 429
        body = resp.json()
        assert body["message"] == (
            "Bạn đã dùng hết lượt hỏi trợ lý hôm nay, vui lòng quay lại vào ngày mai."
        )
        assert body["errors"] == {"retry_after_seconds": 86400}
    assert redis.expires[f"ratelimit:chat_daily:{user_id}"] == 86400


def test_chat_daily_limit_default_is_200():
    assert get_settings().chat_daily_limit == 200
