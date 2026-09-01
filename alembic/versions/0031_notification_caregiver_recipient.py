"""notification_deliveries: allow a caregiver_link as the recipient.

Caregiver Telegram sends reuse this table's send-log shape (channel,
template_code, provider_message_id, status, attempt_no, idempotency_key)
rather than duplicating a second retry state machine. The only structural
gap is recipient_user_id being a NOT NULL FK to users -- a caregiver link
has no users row. Widened to allow exactly one of {recipient_user_id,
caregiver_link_id} instead of splitting the table.

Revision ID: 0031_notif_cg_recipient
Revises: 0030_caregiver_telegram
Create Date: 2026-09-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0031_notif_cg_recipient"
down_revision: str | None = "0030_caregiver_telegram"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("notification_deliveries", "recipient_user_id", nullable=True)
    # 20 chars fit every existing status (QUEUED/SENT/FAILED/NO_DEVICE/
    # DELIVERED) but not this feature's SKIPPED_NO_BINDING (19, fits, but
    # narrowly) or BLOCKED_BY_USER (15, fits) -- widened for headroom rather
    # than naming the next status around a 20-char ceiling. A prior version
    # of this feature (Zalo-based) hit this wall at runtime with a 21-char
    # status; widening here is informed by that, not theoretical.
    op.alter_column(
        "notification_deliveries", "status", type_=sa.String(length=30), existing_nullable=False
    )
    # UUID referencing caregiver_links.id -- not the BIGINT telegram_chat_id.
    op.add_column(
        "notification_deliveries",
        sa.Column("caregiver_link_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    # CASCADE, not SET NULL: unlike alert_id/scheduled_dose_id (whose
    # sibling recipient_user_id stays non-null, so nulling them out never
    # conflicts with anything), caregiver_link_id participates in
    # ck_notification_deliveries_recipient_xor itself. A caregiver-only
    # delivery row already has recipient_user_id NULL -- SET NULL here
    # would leave BOTH null on caregiver-link deletion, violating that
    # CHECK immediately (the FK's own implicit UPDATE raises it). A
    # caregiver's delivery history has no meaning once the link itself is
    # gone, so cascading is also the semantically right call.
    op.create_foreign_key(
        "notification_deliveries_caregiver_link_id_fkey",
        "notification_deliveries",
        "caregiver_links",
        ["caregiver_link_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # NOT VALID first: takes only a brief ACCESS EXCLUSIVE lock to add the
    # constraint definition, deferring the full-table scan. This is the
    # highest-volume table in the schema; a validated CHECK added in one
    # step would hold that lock for the whole scan instead of a moment.
    op.execute(
        "ALTER TABLE notification_deliveries ADD CONSTRAINT "
        "ck_notification_deliveries_recipient_xor "
        "CHECK (num_nonnulls(recipient_user_id, caregiver_link_id) = 1) NOT VALID"
    )
    with op.get_context().autocommit_block():
        # VALIDATE takes SHARE UPDATE EXCLUSIVE -- does not block concurrent
        # reads or writes while it scans. Every existing row already has a
        # non-null recipient_user_id and a null caregiver_link_id, so this
        # cannot fail.
        op.execute(
            "ALTER TABLE notification_deliveries "
            "VALIDATE CONSTRAINT ck_notification_deliveries_recipient_xor"
        )
        op.execute(
            "CREATE INDEX CONCURRENTLY ix_notif_deliveries_caregiver_link_created "
            "ON notification_deliveries (caregiver_link_id, created_at DESC) "
            "WHERE caregiver_link_id IS NOT NULL"
        )


def downgrade() -> None:
    op.drop_index("ix_notif_deliveries_caregiver_link_created", table_name="notification_deliveries")
    op.execute(
        "ALTER TABLE notification_deliveries DROP CONSTRAINT ck_notification_deliveries_recipient_xor"
    )
    op.drop_constraint(
        "notification_deliveries_caregiver_link_id_fkey",
        "notification_deliveries",
        type_="foreignkey",
    )
    op.drop_column("notification_deliveries", "caregiver_link_id")
    op.alter_column(
        "notification_deliveries", "status", type_=sa.String(length=20), existing_nullable=False
    )
    op.alter_column("notification_deliveries", "recipient_user_id", nullable=False)
