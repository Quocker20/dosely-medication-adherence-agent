"""add user_devices table for FCM token storage

Stores FCM device tokens per user so the backend can send push
notifications via Firebase Cloud Messaging.

Revision ID: 0013_user_devices
Revises: 0012_notification_grouping
Create Date: 2026-08-22

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0013_user_devices"
down_revision: Union[str, None] = "0012_notification_grouping"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_devices",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("fcm_token", sa.String(255), nullable=False, unique=True),
        sa.Column("device_name", sa.String(100), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("TRUE")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
    )
    # Index để query nhanh: "lấy tất cả token active của 1 user"
    op.create_index("ix_user_devices_user_active", "user_devices", ["user_id", "is_active"])


def downgrade() -> None:
    op.drop_index("ix_user_devices_user_active", table_name="user_devices")
    op.drop_table("user_devices")
