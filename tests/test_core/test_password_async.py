"""P-03: bcrypt must run off the event loop thread."""

import threading

import pytest

from src.core import security


@pytest.mark.asyncio
async def test_hash_and_verify_async_run_in_worker_thread(monkeypatch):
    loop_thread = threading.get_ident()
    seen: list[int] = []

    real_hashpw = security.bcrypt.hashpw
    real_checkpw = security.bcrypt.checkpw

    def spy_hashpw(*a, **k):
        seen.append(threading.get_ident())
        return real_hashpw(*a, **k)

    def spy_checkpw(*a, **k):
        seen.append(threading.get_ident())
        return real_checkpw(*a, **k)

    monkeypatch.setattr(security.bcrypt, "hashpw", spy_hashpw)
    monkeypatch.setattr(security.bcrypt, "checkpw", spy_checkpw)

    hashed = await security.hash_password_async("123456")
    assert await security.verify_password_async("123456", hashed) is True
    assert await security.verify_password_async("000000", hashed) is False

    assert len(seen) == 3
    assert all(t != loop_thread for t in seen)
