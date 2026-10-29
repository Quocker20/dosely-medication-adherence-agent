"""P-01: every Celery task goes through one NullPool session helper."""
import asyncio
import inspect

import pytest
from sqlalchemy import text
from sqlalchemy.pool import NullPool

from src.core.celery_db import task_session


def test_task_session_yields_working_session_and_disposes_engine(monkeypatch):
    from src.core import celery_db

    created = []
    real = celery_db.create_async_engine

    def spy(*args, **kwargs):
        engine = real(*args, **kwargs)
        created.append((engine, kwargs))
        return engine

    monkeypatch.setattr(celery_db, "create_async_engine", spy)

    async def run():
        async with task_session() as session:
            assert (await session.execute(text("select 1"))).scalar() == 1

    # Two asyncio.run calls == two Celery tasks, each with its own event loop.
    asyncio.run(run())
    asyncio.run(run())

    assert len(created) == 2
    for engine, kwargs in created:
        assert kwargs["poolclass"] is NullPool
        assert isinstance(engine.sync_engine.pool, NullPool)


def test_task_session_disposes_engine_on_error(monkeypatch):
    from sqlalchemy.ext.asyncio import AsyncEngine

    disposed = []
    real_dispose = AsyncEngine.dispose

    async def spy_dispose(self, *args, **kwargs):
        disposed.append(True)
        await real_dispose(self, *args, **kwargs)

    monkeypatch.setattr(AsyncEngine, "dispose", spy_dispose)

    async def run():
        async with task_session():
            raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        asyncio.run(run())
    assert disposed == [True]


def test_no_task_module_builds_its_own_engine():
    import src.modules.adherence_review.tasks as review_tasks
    import src.modules.agents.tasks as agent_tasks

    for module in (agent_tasks, review_tasks):
        source = inspect.getsource(module)
        assert "create_async_engine" not in source
        assert "NullPool" not in source
