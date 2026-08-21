"""Add notification grouping metadata to scheduled doses.

Revision ID: 0013_dose_notify_group
Revises: 0012_agent_review
Create Date: 2026-08-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0013_dose_notify_group"
down_revision: str | None = "0012_agent_review"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "scheduled_doses",
        sa.Column(
            "notification_group_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("scheduled_doses", "notification_group_id")
