"""Database session helper shared by every Celery task (audit P-01).

asyncpg connections bind to the event loop that opened them. A Celery worker
runs each task synchronously and ``asyncio.run()`` builds a fresh event loop
per call, so the module-level engine in src.core.database (built against the
import-time loop) raises "got Future attached to a different loop" from the
second task onward. Each task therefore gets its own engine with ``NullPool``
(deliberate: pooling buys nothing for one connection doing one task) that is
disposed when the task finishes.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from src.core.config import get_settings


@asynccontextmanager
async def task_session() -> AsyncIterator[AsyncSession]:
    """Yield a session bound to a throwaway NullPool engine for this event loop."""
    engine = create_async_engine(get_settings().database_url, poolclass=NullPool)
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False, autocommit=False, autoflush=False)
    try:
        async with session_factory() as session:
            yield session
    finally:
        await engine.dispose()
