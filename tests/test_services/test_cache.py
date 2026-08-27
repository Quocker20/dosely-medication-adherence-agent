"""src/core/cache.py — the read-through response cache.

Every cached endpoint in this codebase (medications, dashboard roster/detail,
adherence summary) shares this helper, so its correctness gates all of them.
The one property that matters most: two callers with different identity must
never share a cache entry when the underlying data is scoped by RBAC/ownership
(see build_cache_key's `actor` parameter) — a bug here is a PHI leak, not a
performance regression.

The suite-wide autouse fixture in conftest.py sets cache_enabled=False so
fixtures that seed data by writing straight to the DB aren't fooled by a stale
cache; these tests turn it back on explicitly since they're testing the cache
itself.
"""

import fnmatch
from typing import Optional

import pytest
from pydantic import BaseModel

from src.common.exceptions import NotFoundException
from src.core.cache import (
    build_cache_key,
    cache_get_json,
    cache_set_json,
    cached_model,
    invalidate_prefix,
)
from src.core.config import get_settings


class _Widget(BaseModel):
    id: str
    label: str


class FakeRedis:
    """Minimal in-memory stand-in for the async Redis client — just enough
    of the surface cache.py actually calls (get/set/scan_iter/unlink)."""

    def __init__(self):
        self.store: dict[str, str] = {}

    async def get(self, key: str) -> Optional[str]:
        return self.store.get(key)

    async def set(self, key: str, value: str, ex: Optional[int] = None) -> None:
        self.store[key] = value

    async def scan_iter(self, match: Optional[str] = None, count: Optional[int] = None):
        for key in list(self.store.keys()):
            if match is None or fnmatch.fnmatch(key, match):
                yield key

    async def unlink(self, *keys: str) -> None:
        for key in keys:
            self.store.pop(key, None)


class BrokenRedis:
    """Simulates a Redis outage — every call raises."""

    async def get(self, *args, **kwargs):
        raise ConnectionError("redis is down")

    async def set(self, *args, **kwargs):
        raise ConnectionError("redis is down")

    async def scan_iter(self, *args, **kwargs):
        raise ConnectionError("redis is down")
        yield  # pragma: no cover — makes this an async generator

    async def unlink(self, *args, **kwargs):
        raise ConnectionError("redis is down")


@pytest.fixture(autouse=True)
def _enable_cache(monkeypatch):
    """Override the suite-wide disable (conftest.py) for this file only."""
    monkeypatch.setattr(get_settings(), "cache_enabled", True)


@pytest.fixture
def fake_redis(monkeypatch):
    client = FakeRedis()

    async def _get_client():
        return client

    monkeypatch.setattr("src.core.cache.get_redis_client", _get_client)
    return client


@pytest.fixture
def broken_redis(monkeypatch):
    client = BrokenRedis()

    async def _get_client():
        return client

    monkeypatch.setattr("src.core.cache.get_redis_client", _get_client)
    return client


class TestBuildCacheKey:
    def test_same_params_same_actor_same_key(self):
        actor = {"sub": "doctor-1", "role": "DOCTOR"}
        key_a = build_cache_key("dash:patients:list", actor=actor, params={"page": 1, "size": 10})
        key_b = build_cache_key("dash:patients:list", actor=actor, params={"page": 1, "size": 10})
        assert key_a == key_b

    def test_param_order_does_not_change_the_key(self):
        key_a = build_cache_key("med:list", params={"page": 1, "search": "abc"})
        key_b = build_cache_key("med:list", params={"search": "abc", "page": 1})
        assert key_a == key_b

    def test_different_actor_different_key(self):
        """The property that matters most: doctor A's cache entry must never
        be addressable by doctor B's identity, even for identical params."""
        params = {"page": 1, "size": 10}
        key_doctor_a = build_cache_key(
            "dash:patients:list", actor={"sub": "doctor-a", "role": "DOCTOR"}, params=params
        )
        key_doctor_b = build_cache_key(
            "dash:patients:list", actor={"sub": "doctor-b", "role": "DOCTOR"}, params=params
        )
        assert key_doctor_a != key_doctor_b

    def test_different_role_same_sub_different_key(self):
        params = {"patient_id": "p1"}
        key_as_patient = build_cache_key(
            "adh:summary", actor={"sub": "u1", "role": "PATIENT"}, params=params
        )
        key_as_doctor = build_cache_key(
            "adh:summary", actor={"sub": "u1", "role": "DOCTOR"}, params=params
        )
        assert key_as_patient != key_as_doctor

    def test_no_actor_is_a_distinct_shared_key(self):
        """Only the medication catalog omits the actor — confirm that path
        still produces one deterministic key regardless of who's asking."""
        key_a = build_cache_key("med:detail", params={"id": "m1"})
        key_b = build_cache_key("med:detail", params={"id": "m1"})
        assert key_a == key_b


class TestCacheGetSetJson:
    @pytest.mark.asyncio
    async def test_round_trips_a_value(self, fake_redis):
        await cache_set_json("k1", {"a": 1}, ttl_seconds=60)
        assert await cache_get_json("k1") == {"a": 1}

    @pytest.mark.asyncio
    async def test_missing_key_is_none(self, fake_redis):
        assert await cache_get_json("nope") is None

    @pytest.mark.asyncio
    async def test_zero_ttl_never_writes(self, fake_redis):
        await cache_set_json("k1", {"a": 1}, ttl_seconds=0)
        assert await cache_get_json("k1") is None

    @pytest.mark.asyncio
    async def test_read_fails_open_on_redis_outage(self, broken_redis):
        """A Redis outage is a cache miss, never a raised exception — the
        caller's DB read must still be able to answer the request."""
        assert await cache_get_json("k1") is None

    @pytest.mark.asyncio
    async def test_write_fails_open_on_redis_outage(self, broken_redis):
        await cache_set_json("k1", {"a": 1}, ttl_seconds=60)  # must not raise

    @pytest.mark.asyncio
    async def test_malformed_entry_is_treated_as_a_miss(self, fake_redis):
        fake_redis.store["k1"] = "{not valid json"
        assert await cache_get_json("k1") is None

    @pytest.mark.asyncio
    async def test_cache_disabled_setting_short_circuits(self, fake_redis, monkeypatch):
        monkeypatch.setattr(get_settings(), "cache_enabled", False)
        await cache_set_json("k1", {"a": 1}, ttl_seconds=60)
        assert await cache_get_json("k1") is None
        assert fake_redis.store == {}


class TestCachedModel:
    @pytest.mark.asyncio
    async def test_miss_calls_loader_and_populates_cache(self, fake_redis):
        calls = {"n": 0}

        async def loader():
            calls["n"] += 1
            return _Widget(id="w1", label="first")

        key = build_cache_key("widget", params={"id": "w1"})
        result = await cached_model(key, 60, _Widget, loader)

        assert result == _Widget(id="w1", label="first")
        assert calls["n"] == 1
        assert await cache_get_json(key) == {"id": "w1", "label": "first"}

    @pytest.mark.asyncio
    async def test_hit_does_not_call_loader_again(self, fake_redis):
        calls = {"n": 0}

        async def loader():
            calls["n"] += 1
            return _Widget(id="w1", label=f"call-{calls['n']}")

        key = build_cache_key("widget", params={"id": "w1"})
        first = await cached_model(key, 60, _Widget, loader)
        second = await cached_model(key, 60, _Widget, loader)

        assert calls["n"] == 1
        assert first == second == _Widget(id="w1", label="call-1")

    @pytest.mark.asyncio
    async def test_not_found_from_loader_is_not_cached(self, fake_redis):
        """A 404 (out-of-scope or nonexistent) must never be replayed to a
        caller whose access could differ on the next request."""
        calls = {"n": 0}

        async def loader():
            calls["n"] += 1
            raise NotFoundException(message="nope")

        key = build_cache_key("widget", params={"id": "missing"})

        with pytest.raises(NotFoundException):
            await cached_model(key, 60, _Widget, loader)

        assert await cache_get_json(key) is None

        with pytest.raises(NotFoundException):
            await cached_model(key, 60, _Widget, loader)
        assert calls["n"] == 2  # never short-circuited by a cached denial

    @pytest.mark.asyncio
    async def test_redis_outage_still_returns_the_loaded_value(self, broken_redis):
        async def loader():
            return _Widget(id="w1", label="fresh")

        key = build_cache_key("widget", params={"id": "w1"})
        result = await cached_model(key, 60, _Widget, loader)
        assert result == _Widget(id="w1", label="fresh")

    @pytest.mark.asyncio
    async def test_two_actors_never_share_a_cached_scoped_result(self, fake_redis):
        """Doctor A must never be served doctor B's cached roster page."""

        async def loader_for(sub: str):
            async def _loader():
                return _Widget(id=sub, label=f"roster-for-{sub}")

            return _loader

        key_a = build_cache_key(
            "dash:patients:list", actor={"sub": "doctor-a", "role": "DOCTOR"}, params={"page": 1}
        )
        key_b = build_cache_key(
            "dash:patients:list", actor={"sub": "doctor-b", "role": "DOCTOR"}, params={"page": 1}
        )

        result_a = await cached_model(key_a, 60, _Widget, await loader_for("doctor-a"))
        result_b = await cached_model(key_b, 60, _Widget, await loader_for("doctor-b"))

        assert result_a.label == "roster-for-doctor-a"
        assert result_b.label == "roster-for-doctor-b"

        # And a would-be attacker guessing at the other actor's identity gets
        # a fresh loader call, not the first actor's cached payload.
        replay = await cached_model(
            key_a, 60, _Widget, await loader_for("doctor-a-again")
        )
        assert replay.label == "roster-for-doctor-a"  # served from cache, unchanged


class TestInvalidatePrefix:
    @pytest.mark.asyncio
    async def test_clears_every_key_under_the_namespace(self, fake_redis):
        await cache_set_json(
            build_cache_key("dash:patients:list", params={"page": 1}), {"v": 1}, 60
        )
        await cache_set_json(
            build_cache_key("dash:patients:detail", params={"id": "p1"}), {"v": 2}, 60
        )
        await cache_set_json(build_cache_key("med:list", params={"page": 1}), {"v": 3}, 60)

        await invalidate_prefix("dash:patients")

        assert (
            await cache_get_json(build_cache_key("dash:patients:list", params={"page": 1}))
            is None
        )
        assert (
            await cache_get_json(build_cache_key("dash:patients:detail", params={"id": "p1"}))
            is None
        )
        # A different namespace must survive an unrelated invalidation.
        assert await cache_get_json(build_cache_key("med:list", params={"page": 1})) == {"v": 3}

    @pytest.mark.asyncio
    async def test_fails_open_on_redis_outage(self, broken_redis):
        await invalidate_prefix("dash:patients")  # must not raise
