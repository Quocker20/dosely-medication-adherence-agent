"""Add interval_days to prescription_items.

Revision ID: 0030_item_interval_days
Revises: 0029_routine_overrides
Create Date: 2026-09-01
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0030_item_interval_days"
down_revision: str | None = "0029_routine_overrides"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE prescription_items ADD COLUMN IF NOT EXISTS interval_days INTEGER NOT NULL DEFAULT 1")
    op.execute("ALTER TABLE prescription_items DROP CONSTRAINT IF EXISTS ck_prescription_items_interval_days")
    op.execute(
        "ALTER TABLE prescription_items ADD CONSTRAINT ck_prescription_items_interval_days "
        "CHECK (interval_days >= 1) NOT VALID"
    )
    op.execute("ALTER TABLE prescription_items VALIDATE CONSTRAINT ck_prescription_items_interval_days")


def downgrade() -> None:
    op.execute("ALTER TABLE prescription_items DROP CONSTRAINT IF EXISTS ck_prescription_items_interval_days")
    op.execute("ALTER TABLE prescription_items DROP COLUMN IF EXISTS interval_days")
