"""Provision the schema of the throwaway test database (O-12).

The production schema is created by docs/database_v1_init.sql and then advanced
by Alembic (see alembic/env.py), so the test database is built the same way:
reset the public schema, apply the init SQL, run ``alembic upgrade head``.

Refuses to touch anything that is not the local test database
(tests/db_guard.py). Settings come from .env.test, never from .env.

Usage: python scripts/db/test_db_setup.py   (after `make test-up`)
"""

import os
import subprocess
import sys
import time
from pathlib import Path

import psycopg2
from dotenv import dotenv_values
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tests.db_guard import assert_test_database  # noqa: E402


def load_test_env() -> dict[str, str]:
    values = {k: v for k, v in dotenv_values(ROOT / ".env.test").items() if v is not None}
    os.environ.update(values)
    return values


def connect(url: str, attempts: int = 30):
    parsed = make_url(url)
    last: Exception | None = None
    for _ in range(attempts):
        try:
            return psycopg2.connect(
                host=parsed.host,
                port=parsed.port or 5432,
                user=parsed.username,
                password=parsed.password,
                dbname=parsed.database,
            )
        except psycopg2.OperationalError as exc:  # server still starting
            last = exc
            time.sleep(1)
    raise SystemExit(f"test database not reachable (run `make test-up`): {last}")


def main() -> None:
    env = load_test_env()
    url = env["DATABASE_URL"]
    assert_test_database(url)

    conn = connect(url)
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute("DROP SCHEMA IF EXISTS public CASCADE; CREATE SCHEMA public;")
        cur.execute((ROOT / "docs" / "database_v1_init.sql").read_text(encoding="utf-8"))
    conn.close()
    print("applied docs/database_v1_init.sql")

    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=ROOT,
        env={**os.environ, **env},
        check=True,
    )
    print("alembic upgrade head: done")


if __name__ == "__main__":
    main()
