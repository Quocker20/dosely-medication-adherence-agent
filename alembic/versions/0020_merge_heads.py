"""merge heads: 0019_user_need_onboarding + 0016_seed_medications

Two independent lines diverged from 0015_agent_run_claim and were never
reconciled: the seed-data migration (0016_seed_medications) and the
onboarding-gate rename (which itself already merged the earlier
0013_user_devices/0015_agent_run_claim split via 0016_merge_heads, then
continued through 0017/0018/0019). `alembic upgrade head` fails with
"Multiple head revisions are present" until this exists. Empty on purpose --
both lines are already independently correct; there is nothing to reconcile
beyond the DAG itself.

Revision ID: 0020_merge_heads
Revises: 0019_user_need_onboarding, 0016_seed_medications
Create Date: 2026-08-29
"""

from collections.abc import Sequence

revision: str = "0020_merge_heads"
down_revision: str | tuple[str, ...] | None = (
    "0019_user_need_onboarding",
    "0016_seed_medications",
)
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
