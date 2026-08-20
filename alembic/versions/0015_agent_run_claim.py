"""Add atomic worker claim timestamp to agent runs.

Revision ID: 0015_agent_run_claim
Revises: 0014_planning_audit
Create Date: 2026-08-21
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0015_agent_run_claim"
down_revision: str | None = "0014_planning_audit"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "agent_runs",
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "agent_runs",
        sa.Column("claim_token", sa.UUID(), nullable=True),
    )
    op.add_column(
        "agent_runs",
        sa.Column("claim_expires_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("agent_runs", "claim_expires_at")
    op.drop_column("agent_runs", "claim_token")
    op.drop_column("agent_runs", "started_at")
