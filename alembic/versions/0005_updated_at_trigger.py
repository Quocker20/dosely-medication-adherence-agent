"""slice4: DB trigger to auto-maintain updated_at, replacing per-statement discipline

Core-style `update()` statements (as opposed to ORM flush) never invoke a
column's Python-side `onupdate=` callable, so every hand-written UPDATE has to
remember to set updated_at itself or it silently goes stale — this already bit
patient_profiles/patient_routines. A trigger fixes it once at the DB layer for
every future writer, ORM or raw SQL, instead of per-call-site discipline.

Revision ID: 0005_updated_at_trg
Revises: 0004_caregiver_uq
Create Date: 2026-08-12

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0005_updated_at_trg"
down_revision: Union[str, None] = "0004_caregiver_uq"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLES = ("patient_profiles", "patient_routines")


def upgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION set_updated_at() RETURNS trigger AS $$
        BEGIN
            NEW.updated_at = NOW();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    for table in _TABLES:
        op.execute(
            f"CREATE TRIGGER trg_{table}_set_updated_at "
            f"BEFORE UPDATE ON {table} "
            f"FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
        )


def downgrade() -> None:
    for table in _TABLES:
        op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_set_updated_at ON {table}")
    op.execute("DROP FUNCTION IF EXISTS set_updated_at()")
