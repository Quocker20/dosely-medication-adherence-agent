"""merge chat-memory and adherence-review branches

Two teams independently created a mergepoint for the same pair of parents
(0019_user_need_onboarding + 0016_seed_medications): 0020_chat_memory from the
chatbot work, and 0020_merge_heads from the adherence work, which then grew the
0021..0024 chain on top. Both were valid, but they left the tree with two heads,
so `alembic upgrade head` failed with "Multiple head revisions are present" and
deploys had to fall back to `upgrade heads`.

This revision rejoins them. No schema change of its own.

Revision ID: 0025_merge_chat_adherence
Revises: 0020_chat_memory, 0024_dose_window_scan_idx
Create Date: 2026-08-29
"""

from collections.abc import Sequence

revision: str = "0025_merge_chat_adherence"
down_revision: str | tuple[str, ...] | None = (
    "0020_chat_memory",
    "0024_dose_window_scan_idx",
)
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
