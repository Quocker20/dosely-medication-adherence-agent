"""Merge notification_grouping and agent_review branches.

Revision ID: 0016_merge_heads
Revises: 0013_user_devices, 0015_agent_run_claim
Create Date: 2026-08-25
"""

from collections.abc import Sequence

revision: str = "0016_merge_heads"
down_revision: tuple[str, ...] | None = ("0013_user_devices", "0015_agent_run_claim")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
