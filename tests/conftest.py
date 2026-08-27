from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from src.core.config import get_settings
from src.main import app
try:
    from src.services.store import store
except ImportError:
    store = None


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


@pytest.fixture(autouse=True)
def reset_store():
    """Mỗi test chạy trên dữ liệu seed sạch — store là in-memory singleton."""
    if store is not None:
        store.reset()
    yield
    if store is not None:
        store.reset()


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
