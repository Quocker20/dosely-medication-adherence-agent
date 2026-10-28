"""SEC-03: Redis-backed login lockout keyed by phone."""

from unittest.mock import AsyncMock, patch

import pytest

from src.core import login_lockout
from src.core.config import get_settings
from tests.fake_redis import FakeRedis

PHONE = "+84900111222"


@pytest.fixture
def redis(monkeypatch):
    monkeypatch.setattr(get_settings(), "rate_limit_enabled", True)
    fake = FakeRedis()
    with patch(
        "src.core.login_lockout.get_redis_client", new=AsyncMock(return_value=fake)
    ):
        yield fake


@pytest.mark.asyncio
async def test_five_failures_lock_for_15_minutes(redis):
    for _ in range(4):
        assert await login_lockout.register_failure(PHONE) == 0
    assert await login_lockout.get_lock_remaining(PHONE) == 0
    assert await login_lockout.register_failure(PHONE) == 900
    assert await login_lockout.get_lock_remaining(PHONE) == 900
    redis.advance(901)
    assert await login_lockout.get_lock_remaining(PHONE) == 0


@pytest.mark.asyncio
async def test_lock_escalates_to_1h_and_is_capped_there(redis):
    durations = []
    for _ in range(4):
        for _ in range(4):
            await login_lockout.register_failure(PHONE)
        durations.append(await login_lockout.register_failure(PHONE))
        redis.advance(durations[-1] + 1)
    assert durations == [900, 3600, 3600, 3600]


@pytest.mark.asyncio
async def test_success_resets_failure_counter(redis):
    for _ in range(4):
        await login_lockout.register_failure(PHONE)
    await login_lockout.reset_failures(PHONE)
    for _ in range(4):
        assert await login_lockout.register_failure(PHONE) == 0
    assert await login_lockout.register_failure(PHONE) == 900


@pytest.mark.asyncio
async def test_failure_window_expires(redis):
    for _ in range(4):
        await login_lockout.register_failure(PHONE)
    redis.advance(login_lockout.FAIL_WINDOW_SECONDS + 1)
    assert await login_lockout.register_failure(PHONE) == 0


@pytest.mark.asyncio
async def test_fail_open_when_redis_down(monkeypatch, caplog):
    monkeypatch.setattr(get_settings(), "rate_limit_enabled", True)
    with (
        patch(
            "src.core.login_lockout.get_redis_client",
            new=AsyncMock(side_effect=ConnectionError("down")),
        ),
        caplog.at_level("WARNING"),
    ):
        assert await login_lockout.get_lock_remaining(PHONE) == 0
        assert await login_lockout.register_failure(PHONE) == 0
        await login_lockout.reset_failures(PHONE)
    assert any(r.levelname == "WARNING" for r in caplog.records)


def test_lock_message_formats_minutes_and_hours():
    assert "15 phút" in login_lockout.lock_message(900)
    assert "1 phút" in login_lockout.lock_message(30)
    assert "1 giờ" in login_lockout.lock_message(3600)
    assert login_lockout.lock_message(900).startswith("Bạn đã nhập sai quá nhiều lần.")
