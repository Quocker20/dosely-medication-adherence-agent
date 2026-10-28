import logging
from collections.abc import AsyncGenerator
from typing import Any

from sqlalchemy.ext.asyncio import (
    AsyncAttrs,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from src.core.config import get_settings

logger = logging.getLogger(__name__)

settings = get_settings()


def build_engine_kwargs(cfg: Any) -> dict[str, Any]:
    """Engine options for the main (API) engine: pre-ping, recycle, pool size.

    Celery tasks use their own NullPool engines (``celery_db``) and are not
    affected.
    """
    kwargs: dict[str, Any] = {
        "echo": cfg.sql_echo,
        "future": True,
        "pool_pre_ping": True,
        "pool_recycle": cfg.db_pool_recycle_seconds,
        "pool_size": cfg.db_pool_size,
        "max_overflow": cfg.db_max_overflow,
        "pool_timeout": cfg.db_pool_timeout_seconds,
    }
    if cfg.db_disable_statement_cache:
        # pgbouncer transaction pooling: no server-side prepared statements.
        kwargs["connect_args"] = {"statement_cache_size": 0}
        logger.info("asyncpg statement cache disabled (DB_DISABLE_STATEMENT_CACHE=true)")
    return kwargs


engine = create_async_engine(settings.database_url, **build_engine_kwargs(settings))

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


class Base(AsyncAttrs, DeclarativeBase):
    """Base class for all SQLAlchemy ORM models."""
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency yielding an async database session.

    Transaction management is NOT handled here. Service layer is responsible
    for explicit transaction boundaries via ``async with session.begin():``.
    """
    async with AsyncSessionLocal() as session:
        yield session
