"""caregiver_links: reshape from an actor (users FK) to a Telegram-notified
contact record.

Caregivers no longer log in or hold a users row. The link now carries a
phone (doctor contact only -- Telegram addresses by chat_id, never phone),
an optional one-time link_code for bot binding via deep link, and the
Telegram interaction bookkeeping. The single pre-existing row is confirmed
fake test data and is deleted rather than migrated -- its caregiver_user_id
would point at a placeholder account this feature no longer creates.

Revision ID: 0030_caregiver_telegram
Revises: 0029_routine_overrides
Create Date: 2026-09-01
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0030_caregiver_telegram"
down_revision: str | None = "0029_routine_overrides"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Confirmed fake test data (single row) -- deleted, not migrated. Its
    # caregiver_user_id points at a placeholder account this feature no
    # longer provisions, so there is nothing meaningful to carry forward.
    op.execute("DELETE FROM caregiver_links")

    op.drop_constraint(
        "uq_caregiver_links_patient_caregiver", "caregiver_links", type_="unique"
    )
    op.drop_constraint(
        "caregiver_links_caregiver_user_id_fkey", "caregiver_links", type_="foreignkey"
    )
    op.drop_column("caregiver_links", "caregiver_user_id")
    op.drop_column("caregiver_links", "channels")

    op.add_column("caregiver_links", sa.Column("phone", sa.String(length=20), nullable=True))
    op.execute("UPDATE caregiver_links SET phone = '' WHERE phone IS NULL")
    op.alter_column("caregiver_links", "phone", nullable=False)

    op.add_column("caregiver_links", sa.Column("link_code", sa.String(length=8), nullable=True))
    # BIGINT, not INTEGER -- Telegram chat ids exceeded 32 bits in 2021.
    op.add_column("caregiver_links", sa.Column("telegram_chat_id", sa.BigInteger(), nullable=True))
    op.add_column(
        "caregiver_links",
        sa.Column("telegram_bound_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "caregiver_links",
        sa.Column("telegram_last_interaction_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "caregiver_links",
        sa.Column("last_report_sent_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "caregiver_links",
        sa.Column("last_message_sent_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.alter_column(
        "caregiver_links", "status", server_default="PENDING_BINDING"
    )
    op.execute(
        "ALTER TABLE caregiver_links ADD CONSTRAINT ck_caregiver_links_status "
        "CHECK (status IN ('PENDING_BINDING','ACTIVE','BLOCKED','INACTIVE'))"
    )

    # CONCURRENTLY cannot run inside a transaction; autocommit_block() lifts
    # that for this migration only, matching 0004_caregiver_links_unique.
    with op.get_context().autocommit_block():
        op.execute(
            "CREATE UNIQUE INDEX CONCURRENTLY uq_caregiver_links_patient_phone "
            "ON caregiver_links (patient_id, phone)"
        )
        # Partial unique index -- kept as a plain index, never attached as a
        # named constraint: Postgres rejects ADD CONSTRAINT ... UNIQUE USING
        # INDEX on a partial index (WrongObjectTypeError). The uniqueness
        # guarantee is identical either way; only the constraint-catalog
        # entry is missing.
        op.execute(
            "CREATE UNIQUE INDEX CONCURRENTLY uq_caregiver_links_link_code "
            "ON caregiver_links (link_code) WHERE link_code IS NOT NULL"
        )
        op.execute(
            "CREATE INDEX CONCURRENTLY ix_caregiver_links_telegram_chat_id "
            "ON caregiver_links (telegram_chat_id) WHERE telegram_chat_id IS NOT NULL"
        )
        # Backs the nightly report claim scan (stage 9): only bound links
        # can ever be sent to, so the partial predicate keeps every unbound
        # row (the majority during rollout) out of the index entirely.
        # Single column, not composite -- Telegram has no CS window to also
        # gate on.
        op.execute(
            "CREATE INDEX CONCURRENTLY ix_caregiver_links_report_due "
            "ON caregiver_links (last_report_sent_at) "
            "WHERE telegram_chat_id IS NOT NULL"
        )
    op.execute(
        "ALTER TABLE caregiver_links ADD CONSTRAINT uq_caregiver_links_patient_phone "
        "UNIQUE USING INDEX uq_caregiver_links_patient_phone"
    )


def downgrade() -> None:
    op.drop_constraint("uq_caregiver_links_patient_phone", "caregiver_links", type_="unique")
    op.drop_index("uq_caregiver_links_link_code", table_name="caregiver_links")
    op.drop_index("ix_caregiver_links_telegram_chat_id", table_name="caregiver_links")
    op.drop_index("ix_caregiver_links_report_due", table_name="caregiver_links")

    op.execute("ALTER TABLE caregiver_links DROP CONSTRAINT ck_caregiver_links_status")
    op.alter_column("caregiver_links", "status", server_default="ACTIVE")

    op.drop_column("caregiver_links", "last_message_sent_at")
    op.drop_column("caregiver_links", "last_report_sent_at")
    op.drop_column("caregiver_links", "telegram_last_interaction_at")
    op.drop_column("caregiver_links", "telegram_bound_at")
    op.drop_column("caregiver_links", "telegram_chat_id")
    op.drop_column("caregiver_links", "link_code")
    op.drop_column("caregiver_links", "phone")

    op.add_column(
        "caregiver_links",
        sa.Column("channels", sa.dialects.postgresql.JSONB(), nullable=False, server_default="[]"),
    )
    op.add_column(
        "caregiver_links", sa.Column("caregiver_user_id", sa.dialects.postgresql.UUID(), nullable=True)
    )
    op.create_foreign_key(
        "caregiver_links_caregiver_user_id_fkey",
        "caregiver_links",
        "users",
        ["caregiver_user_id"],
        ["id"],
        ondelete="CASCADE",
    )
    # Data is not restorable -- the downgrade only restores shape, and the
    # restored NOT NULL below requires the table to be empty (it is, this
    # migration's upgrade() only ever emptied it).
    op.alter_column("caregiver_links", "caregiver_user_id", nullable=False)
    op.create_unique_constraint(
        "uq_caregiver_links_patient_caregiver",
        "caregiver_links",
        ["patient_id", "caregiver_user_id"],
    )
