"""Persist the human-readable reason an agent run stopped.

error_code only ever held the exception class name (e.g. "ScheduleConstraintError"),
so the message that names the offending item and the actual gap was written to the
log and then lost. A doctor looking at a NEEDS_REVIEW schedule in the portal had no
way to see which medication broke which constraint.

Revision ID: 0017_agent_run_error_message
Revises: 0016_merge_heads
Create Date: 2026-08-26
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0017_agent_run_error_message"
down_revision: str | None = "0016_merge_heads"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "agent_runs",
        sa.Column("error_message", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("agent_runs", "error_message")
