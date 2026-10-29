"""Refuse to let the test suite near a database it does not own (O-12).

Many tests DELETE rows, and scripts/db/test_db_setup.py drops the whole public
schema. Both are only acceptable against the throwaway database started by
docker-compose.test.yml, so every destructive entry point calls
``assert_test_database`` first.
"""

from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
TEST_DB_SUFFIX = "_test"


class UnsafeTestDatabaseError(RuntimeError):
    """DATABASE_URL does not point at the local test database."""


def assert_test_database(url: str) -> None:
    """Raise unless ``url`` is a loopback Postgres whose database name ends in ``_test``."""
    try:
        parsed = make_url(url)
    except ArgumentError:
        raise UnsafeTestDatabaseError("DATABASE_URL is not a parseable database URL") from None

    problems = []
    if not parsed.drivername.startswith("postgresql"):
        problems.append(f"driver {parsed.drivername!r} is not PostgreSQL")
    if (parsed.host or "") not in LOCAL_HOSTS:
        problems.append(f"host {parsed.host!r} is not loopback")
    if not (parsed.database or "").endswith(TEST_DB_SUFFIX):
        problems.append(f"database {parsed.database!r} does not end with {TEST_DB_SUFFIX!r}")
    if problems:
        raise UnsafeTestDatabaseError(
            "Refusing to run tests against "
            f"{parsed.render_as_string(hide_password=True)}: " + "; ".join(problems)
            + ". Use `make test-up` and .env.test."
        )
