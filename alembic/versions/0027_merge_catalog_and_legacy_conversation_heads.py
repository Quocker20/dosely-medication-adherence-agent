"""Merge catalog seed and legacy conversation cleanup heads.

Both 0026 revisions are independent and must be recorded before future
migrations. This merge revision contains no DDL; it restores a single Alembic
head so deployment can continue to use ``alembic upgrade head``.

Revision ID: 0027_merge_catalog_and_legacy_conversation_heads
Revises: 0026_drop_legacy_conversations, 0026_seed_curated_products
Create Date: 2026-08-31
"""

from collections.abc import Sequence

revision: str = "0027_merge_catalog_and_legacy_conversation_heads"
down_revision: str | tuple[str, ...] | None = (
    "0026_drop_legacy_conversations",
    "0026_seed_curated_products",
)
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Merge independent migration heads without changing schema."""


def downgrade() -> None:
    """Restore the independent migration heads without changing schema."""
