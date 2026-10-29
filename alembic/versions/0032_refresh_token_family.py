"""refresh_tokens: token family + rotation marker for reuse detection (SEC-19).

family_id groups every token descended from one login, so detecting reuse of an
already-rotated token can revoke the whole session in one UPDATE. rotated_at
distinguishes "revoked because it was exchanged for a new one" (reuse is a theft
signal, except inside a short grace window) from "revoked by logout / PIN
change" (plain rejection). replaced_by_id records the rotation chain.

Existing rows become their own single-token family (family_id = id).

Revision ID: 0032_refresh_token_family
Revises: 0031_notif_cg_recipient
Create Date: 2026-10-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0032_refresh_token_family"
down_revision: str | None = "0031_notif_cg_recipient"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "refresh_tokens",
        sa.Column("family_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "refresh_tokens",
        sa.Column("rotated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "refresh_tokens",
        sa.Column("replaced_by_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.execute("UPDATE refresh_tokens SET family_id = id WHERE family_id IS NULL")
    op.alter_column(
        "refresh_tokens",
        "family_id",
        nullable=False,
        server_default=sa.text("gen_random_uuid()"),
    )
    op.create_index("idx_refresh_tokens_family", "refresh_tokens", ["family_id"])


def downgrade() -> None:
    op.drop_index("idx_refresh_tokens_family", table_name="refresh_tokens")
    op.drop_column("refresh_tokens", "replaced_by_id")
    op.drop_column("refresh_tokens", "rotated_at")
    op.drop_column("refresh_tokens", "family_id")
