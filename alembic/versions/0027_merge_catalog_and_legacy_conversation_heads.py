"""Merge catalog seed and legacy conversation cleanup heads.

Both 0026 revisions are independent and must be recorded before future
migrations. This merge revision contains no DDL; it restores a single Alembic
head so deployment can continue to use ``alembic upgrade head``.

Revision ID: 0027_merge_catalog_legacy
Revises: 0026_drop_legacy_conversations, 0026_seed_curated_products
Create Date: 2026-08-31

The revision id is deliberately short: alembic_version.version_num is
VARCHAR(32), and the original id ("0027_merge_catalog_and_legacy_conversation_
heads", 48 chars) overflowed it, so the DDL ran but the version stamp failed and
the whole upgrade rolled back. Filename kept as-is — this repo already has
precedent for filename != revision id (e.g. 0016_seed_medication_catalog.py ->
"0016_seed_medications"). Keep every future revision id <= 32 chars.
"""

from collections.abc import Sequence

revision: str = "0027_merge_catalog_legacy"
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
