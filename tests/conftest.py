"""Test configuration.

Environment bootstrap (O-12): the suite runs against the throwaway Postgres +
Redis from docker-compose.test.yml, never a developer's or production's
database. ``.env.test`` is force-loaded BEFORE anything under ``src`` is
imported (Settings is cached on first use), overriding the shell and ignoring
any local ``.env``. ``pytest_configure`` then aborts the whole session unless
DATABASE_URL points at the test database.
"""

import os
from pathlib import Path

import pytest
from dotenv import dotenv_values

ENV_TEST_PATH = Path(__file__).resolve().parent.parent / ".env.test"

for _key, _value in dotenv_values(ENV_TEST_PATH).items():
    if _value is not None:
        os.environ[_key] = _value

# src.main only mounts /downloads when the directory exists, and downloads/ is
# gitignored, so a clean checkout would 500 on /api/v1/app/latest-version
# (url_for("downloads")). Create it before the app is imported.
(ENV_TEST_PATH.parent / "downloads").mkdir(exist_ok=True)

from unittest.mock import AsyncMock  # noqa: E402

import pytest_asyncio  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402

from src.core.config import Settings, get_settings  # noqa: E402
from tests.db_guard import UnsafeTestDatabaseError, assert_test_database  # noqa: E402

# A developer's real .env (possibly pointing at Supabase) must not leak in:
# only .env.test and explicit process env feed Settings during tests.
Settings.model_config["env_file"] = None

from src.main import app  # noqa: E402


def pytest_configure(config):
    try:
        assert_test_database(get_settings().database_url)
    except UnsafeTestDatabaseError as exc:
        pytest.exit(str(exc), returncode=3)


@pytest.fixture(autouse=True)
def disable_rate_limit(monkeypatch):
    monkeypatch.setattr(get_settings(), "rate_limit_enabled", False)


@pytest.fixture(autouse=True)
def disable_response_cache():
    """Several test fixtures (test_dashboard.py's _add_alert/_add_survey,
    among others) seed rows directly through the DB session, bypassing the
    service-layer cache invalidation calls entirely. Caching is a production
    concern (src/core/cache.py); the suite needs every GET to see the latest
    row regardless of how it got written, so keep the read-through cache off
    for the duration of each test."""
    settings = get_settings()
    original = settings.cache_enabled
    settings.cache_enabled = False
    yield
    settings.cache_enabled = original


@pytest_asyncio.fixture
async def client():
    """Async HTTP client for testing API endpoints."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def mock_llm():
    """Mock LLM to avoid calling OpenAI during tests.

    Usage in test:
        def test_something(mock_llm):
            # LLM calls will return mock response instead of hitting OpenAI
            ...
    """
    mock = AsyncMock()
    mock.ainvoke.return_value = AsyncMock(content="Mocked LLM response")
    return mock
