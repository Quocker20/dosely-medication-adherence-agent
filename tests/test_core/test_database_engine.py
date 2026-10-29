"""P-05: main engine pool configuration."""
from types import SimpleNamespace

from src.core.database import build_engine_kwargs


def _cfg(**over):
    base = dict(
        sql_echo=False,
        db_pool_size=5,
        db_max_overflow=10,
        db_pool_recycle_seconds=1800,
        db_pool_timeout_seconds=30,
        db_disable_statement_cache=False,
    )
    base.update(over)
    return SimpleNamespace(**base)


def test_pool_kwargs_defaults():
    kw = build_engine_kwargs(_cfg())
    assert kw["pool_pre_ping"] is True
    assert kw["pool_recycle"] == 1800
    assert kw["pool_size"] == 5
    assert kw["max_overflow"] == 10
    assert kw["echo"] is False
    assert "connect_args" not in kw


def test_sql_echo_kept_and_sizes_from_settings():
    kw = build_engine_kwargs(_cfg(sql_echo=True, db_pool_size=3, db_max_overflow=0))
    assert kw["echo"] is True and kw["pool_size"] == 3 and kw["max_overflow"] == 0


def test_statement_cache_disabled_when_configured():
    kw = build_engine_kwargs(_cfg(db_disable_statement_cache=True))
    assert kw["connect_args"] == {"statement_cache_size": 0}


def test_real_engine_uses_pre_ping():
    from src.core.database import engine

    assert engine.sync_engine.pool._pre_ping is True
