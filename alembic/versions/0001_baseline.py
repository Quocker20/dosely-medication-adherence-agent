"""baseline: mark existing 24-table schema (created via database_v1_init.sql) as alembic head

No DDL here. DB was provisioned by docker-entrypoint-initdb.d/init.sql, not alembic.
This revision exists purely so `alembic stamp 0001_baseline` gives the live DB a
version row, letting later migrations chain forward without alembic trying to
recreate tables that already exist.

Revision ID: 0001_baseline
Revises:
Create Date: 2026-08-11

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0001_baseline"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
