"""SEC-19: refresh token rotation, reuse detection, grace window."""

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import update

from src.core.database import AsyncSessionLocal, engine
from src.modules.auth.models import RefreshToken
from src.modules.auth.repository import AuthRepository
from tests.test_api.test_auth import _cleanup, _create_doctor, _login

PHONE = "+84900600801"
PIN = "123456"


@pytest_asyncio.fixture(autouse=True)
async def _dispose_engine_pool():
    yield
    await engine.dispose()


async def _refresh(client, token):
    return await client.post("/api/v1/auth/refresh", json={"refresh_token": token})


async def _age_rotation(token: str, seconds: int) -> None:
    """Pretend the token was rotated `seconds` ago."""
    async with AsyncSessionLocal() as db:
        async with db.begin():
            await db.execute(
                update(RefreshToken)
                .where(RefreshToken.token_hash == AuthRepository.hash_token(token))
                .values(rotated_at=datetime.now(UTC) - timedelta(seconds=seconds))
            )


@pytest.mark.asyncio
async def test_refresh_rotates_token_and_revokes_old_one(client):
    user_id = await _create_doctor(PHONE, PIN, "Dr Rot", "LIC-ROT-1")
    try:
        first = await _login(client, PHONE, PIN)
        r = await _refresh(client, first["refresh_token"])
        assert r.status_code == 200
        second = r.json()["data"]
        assert second["refresh_token"] != first["refresh_token"]

        async with AsyncSessionLocal() as db:
            repo = AuthRepository(db)
            old = await repo.get_refresh_token_any_state(
                AuthRepository.hash_token(first["refresh_token"])
            )
            new = await repo.get_refresh_token_any_state(
                AuthRepository.hash_token(second["refresh_token"])
            )
        assert old.revoked_at is not None and old.rotated_at is not None
        assert new.revoked_at is None
        assert new.family_id == old.family_id
        assert old.replaced_by_id == new.id
    finally:
        await _cleanup([user_id], [])


@pytest.mark.asyncio
async def test_reuse_after_grace_revokes_whole_family(client):
    user_id = await _create_doctor(PHONE, PIN, "Dr Rot", "LIC-ROT-2")
    try:
        first = await _login(client, PHONE, PIN)
        second = (await _refresh(client, first["refresh_token"])).json()["data"]
        await _age_rotation(first["refresh_token"], 120)

        stolen = await _refresh(client, first["refresh_token"])
        assert stolen.status_code == 401

        # The legitimately rotated token is dead too: whole session revoked.
        after = await _refresh(client, second["refresh_token"])
        assert after.status_code == 401
    finally:
        await _cleanup([user_id], [])


@pytest.mark.asyncio
async def test_reuse_within_grace_returns_fresh_pair_without_revocation(client):
    user_id = await _create_doctor(PHONE, PIN, "Dr Rot", "LIC-ROT-3")
    try:
        first = await _login(client, PHONE, PIN)
        second = (await _refresh(client, first["refresh_token"])).json()["data"]

        retry = await _refresh(client, first["refresh_token"])  # lost-response retry
        assert retry.status_code == 200
        third = retry.json()["data"]
        assert third["refresh_token"] not in (first["refresh_token"], second["refresh_token"])

        # Neither pair is revoked; both continue to work.
        assert (await _refresh(client, third["refresh_token"])).status_code == 200
        assert (await _refresh(client, second["refresh_token"])).status_code == 200
    finally:
        await _cleanup([user_id], [])


@pytest.mark.asyncio
async def test_concurrent_refresh_with_same_token_never_revokes_session(client):
    user_id = await _create_doctor(PHONE, PIN, "Dr Rot", "LIC-ROT-4")
    try:
        first = await _login(client, PHONE, PIN)
        results = await asyncio.gather(
            *[_refresh(client, first["refresh_token"]) for _ in range(4)]
        )
        assert [r.status_code for r in results] == [200] * 4
        tokens = {r.json()["data"]["refresh_token"] for r in results}
        assert len(tokens) == 4
    finally:
        await _cleanup([user_id], [])


@pytest.mark.asyncio
async def test_refresh_after_logout_is_plain_rejection(client):
    user_id = await _create_doctor(PHONE, PIN, "Dr Rot", "LIC-ROT-5")
    try:
        body = await _login(client, PHONE, PIN)
        headers = {"Authorization": f"Bearer {body['access_token']}"}
        out = await client.post(
            "/api/v1/auth/logout",
            json={"refresh_token": body["refresh_token"]},
            headers=headers,
        )
        assert out.status_code == 200
        assert (await _refresh(client, body["refresh_token"])).status_code == 401
    finally:
        await _cleanup([user_id], [])
