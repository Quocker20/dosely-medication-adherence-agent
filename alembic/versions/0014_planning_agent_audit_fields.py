"""Add structured Planning Agent audit fields.

Revision ID: 0014_planning_audit
Revises: 0013_dose_notify_group
Create Date: 2026-08-21
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0014_planning_audit"
down_revision: str | None = "0013_dose_notify_group"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("agent_runs", sa.Column("prompt_version", sa.String(length=50), nullable=True))
    op.add_column("agent_runs", sa.Column("input_hash", sa.String(length=64), nullable=True))
    op.add_column("agent_runs", sa.Column("output_hash", sa.String(length=64), nullable=True))
    op.add_column("agent_runs", sa.Column("candidate_source", sa.String(length=64), nullable=True))


def downgrade() -> None:
    op.drop_column("agent_runs", "candidate_source")
    op.drop_column("agent_runs", "output_hash")
    op.drop_column("agent_runs", "input_hash")
    op.drop_column("agent_runs", "prompt_version")
