"""The suite DELETEs rows and recreates schema, so it must refuse to run
against anything that is not the dedicated local test database (O-12)."""

import pytest

from tests.db_guard import UnsafeTestDatabaseError, assert_test_database

SAFE = [
    "postgresql+asyncpg://dosely_test:pw@localhost:5433/dosely_test",
    "postgresql+asyncpg://u:p@127.0.0.1:5433/anything_test",
    "postgresql+psycopg2://u:p@[::1]:5433/x_test",
]

UNSAFE = [
    # Supabase / remote hosts, even with a _test-looking name
    "postgresql+asyncpg://postgres:pw@db.abcdefgh.supabase.co:5432/postgres",
    "postgresql+asyncpg://u:p@db.example.com:5432/dosely_test",
    # local host but not a test database
    "postgresql+asyncpg://u:p@localhost:5432/dosely",
    "postgresql+asyncpg://u:p@localhost:5433/postgres",
    # sqlite or garbage
    "sqlite+aiosqlite:///./data/dev.db",
    "",
    "not a url",
]


@pytest.mark.parametrize("url", SAFE)
def test_accepts_local_test_database(url):
    assert_test_database(url)


@pytest.mark.parametrize("url", UNSAFE)
def test_refuses_everything_else(url):
    with pytest.raises(UnsafeTestDatabaseError):
        assert_test_database(url)


def test_error_never_leaks_the_password():
    url = "postgresql+asyncpg://postgres:s3cr3t-pw@db.example.com:5432/postgres"
    with pytest.raises(UnsafeTestDatabaseError) as exc:
        assert_test_database(url)
    assert "s3cr3t-pw" not in str(exc.value)
