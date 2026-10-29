"""SEC-03 end-to-end: lockout through POST /auth/login."""

from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from sqlalchemy import delete, select

from src.core.config import get_settings
from src.core.database import AsyncSessionLocal, engine
from src.modules.admin.models import AuditLog, DoctorProfile
from src.modules.auth.models import User
from tests.fake_redis import FakeRedis
from tests.test_api.test_auth import _create_doctor

PHONE = "+84900600777"
PIN = "123456"


@pytest_asyncio.fixture(autouse=True)
async def _dispose_engine_pool():
    yield
    await engine.dispose()


@pytest.fixture
def lockout_redis(monkeypatch):
    monkeypatch.setattr(get_settings(), "rate_limit_enabled", True)
    lockout, limiter = FakeRedis(), FakeRedis()
    with (
        patch("src.core.login_lockout.get_redis_client", new=AsyncMock(return_value=lockout)),
        patch("src.core.rate_limit.get_redis_client", new=AsyncMock(return_value=limiter)),
    ):
        yield lockout, limiter


async def _post(client, phone, pin):
    return await client.post("/api/v1/auth/login", json={"phone": phone, "password": pin})


async def _cleanup(user_id):
    async with AsyncSessionLocal() as db:
        async with db.begin():
            await db.execute(delete(AuditLog).where(AuditLog.entity_type == "auth"))
            await db.execute(delete(DoctorProfile).where(DoctorProfile.user_id == user_id))
            await db.execute(delete(User).where(User.id == user_id))


@pytest.mark.asyncio
async def test_lockout_after_five_wrong_pins_and_generic_shape(client, lockout_redis):
    lockout, limiter = lockout_redis
    user_id = await _create_doctor(PHONE, PIN, "Dr Lock", "LIC-LOCK-1")
    try:
        unknown = await _post(client, "+84900600778", "000000")
        wrong = await _post(client, PHONE, "000000")
        assert unknown.status_code == wrong.status_code == 401
        assert unknown.json()["message"] == wrong.json()["message"]
        assert unknown.json()["errors"] == wrong.json()["errors"]

        for _ in range(3):
            limiter.advance(61)
            assert (await _post(client, PHONE, "000000")).status_code == 401
        limiter.advance(61)
        fifth = await _post(client, PHONE, "000000")
        assert fifth.status_code == 429
        body = fifth.json()
        assert body["errors"] == {"retry_after_seconds": 900}
        assert body["message"] == "Bạn đã nhập sai quá nhiều lần. Vui lòng thử lại sau 15 phút."

        # Correct PIN is refused while locked.
        limiter.advance(61)
        locked = await _post(client, PHONE, PIN)
        assert locked.status_code == 429
        assert 0 < locked.json()["errors"]["retry_after_seconds"] <= 900

        # After the lock expires the correct PIN works and resets the counter.
        lockout.advance(901)
        limiter.advance(61)
        ok = await _post(client, PHONE, PIN)
        assert ok.status_code == 200
    finally:
        await _cleanup(user_id)


@pytest.mark.asyncio
async def test_failed_logins_are_audited_without_pin(client, lockout_redis):
    user_id = await _create_doctor(PHONE, PIN, "Dr Audit", "LIC-LOCK-2")
    try:
        assert (await _post(client, PHONE, "654321")).status_code == 401
        async with AsyncSessionLocal() as db:
            rows = (
                await db.execute(
                    select(AuditLog).where(AuditLog.action == "LOGIN_FAILED")
                )
            ).scalars().all()
        assert rows
        row = rows[-1]
        assert row.actor_user_id == user_id
        assert "654321" not in str(row.new_values)
        assert row.new_values["reason"] == "wrong_pin"
        assert PHONE not in str(row.new_values)
    finally:
        await _cleanup(user_id)


@pytest.mark.asyncio
async def test_login_works_when_redis_is_down(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "rate_limit_enabled", True)
    user_id = await _create_doctor(PHONE, PIN, "Dr Down", "LIC-LOCK-3")
    down = AsyncMock(side_effect=ConnectionError("down"))
    try:
        with (
            patch("src.core.login_lockout.get_redis_client", new=down),
            patch("src.core.rate_limit.get_redis_client", new=down),
        ):
            assert (await _post(client, PHONE, "000000")).status_code == 401
            assert (await _post(client, PHONE, PIN)).status_code == 200
    finally:
        await _cleanup(user_id)


@pytest.mark.asyncio
async def test_malformed_pin_spends_bcrypt_and_counts_as_failure(client, lockout_redis):
    user_id = await _create_doctor(PHONE, PIN, "Dr Malformed", "LIC-LOCK-3")
    try:
        with patch(
            "src.modules.auth.service.verify_password_async",
            new=AsyncMock(return_value=False),
        ) as verify:
            resp = await _post(client, PHONE, "abc")
        assert resp.status_code == 401
        assert resp.json()["message"] == "Invalid phone number or password"
        verify.assert_awaited_once()

        # Malformed input counts towards the lockout like a wrong PIN.
        _, limiter = lockout_redis
        for _ in range(3):
            limiter.advance(61)
            assert (await _post(client, PHONE, "abc")).status_code == 401
        limiter.advance(61)
        assert (await _post(client, PHONE, "abc")).status_code == 429
    finally:
        await _cleanup(user_id)
