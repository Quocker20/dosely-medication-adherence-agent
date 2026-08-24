"""notification dose grouping junction table and indexes

Supports grouping multiple scheduled doses into a single consolidated
notification delivery (Option A: notification_dose_items junction table).
Enables batch notifications and synchronized snooze across concurrent medications.

Revision ID: 0012_notification_grouping
Revises: 0011_schedule_snapshots
Create Date: 2026-08-19

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0012_notification_grouping"
down_revision: Union[str, None] = "0011_schedule_snapshots"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Ensure notification_deliveries table exists
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS notification_deliveries (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            scheduled_dose_id UUID REFERENCES scheduled_doses(id) ON DELETE SET NULL,
            alert_id UUID REFERENCES alerts(id) ON DELETE SET NULL,
            recipient_user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            channel VARCHAR(20) NOT NULL,
            template_code VARCHAR(50) NOT NULL,
            title VARCHAR(255),
            body TEXT,
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
            provider_message_id VARCHAR(255),
            status VARCHAR(20) NOT NULL DEFAULT 'QUEUED',
            attempt_no SMALLINT NOT NULL DEFAULT 1,
            scheduled_at TIMESTAMPTZ NOT NULL,
            sent_at TIMESTAMPTZ,
            delivered_at TIMESTAMPTZ,
            idempotency_key VARCHAR(100) UNIQUE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )

    # Add columns to notification_deliveries if table already existed without them
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns 
                WHERE table_name = 'notification_deliveries' AND column_name = 'title'
            ) THEN
                ALTER TABLE notification_deliveries ADD COLUMN title VARCHAR(255);
            END IF;
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns 
                WHERE table_name = 'notification_deliveries' AND column_name = 'body'
            ) THEN
                ALTER TABLE notification_deliveries ADD COLUMN body TEXT;
            END IF;
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns 
                WHERE table_name = 'notification_deliveries' AND column_name = 'metadata'
            ) THEN
                ALTER TABLE notification_deliveries ADD COLUMN metadata JSONB NOT NULL DEFAULT '{}'::jsonb;
            END IF;
        END $$;
        """
    )

    # Create junction table for 1-to-N notification to scheduled doses
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS notification_dose_items (
            notification_delivery_id UUID NOT NULL REFERENCES notification_deliveries(id) ON DELETE CASCADE,
            scheduled_dose_id UUID NOT NULL REFERENCES scheduled_doses(id) ON DELETE CASCADE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT pk_notification_dose_items PRIMARY KEY (notification_delivery_id, scheduled_dose_id)
        )
        """
    )

    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_notif_dose_items_dose_id 
        ON notification_dose_items(scheduled_dose_id)
        """
    )

    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_notif_deliveries_recipient_scheduled 
        ON notification_deliveries(recipient_user_id, scheduled_at)
        """
    )


def downgrade() -> None:
    # Intentionally only drop the junction table and newly added index.
    # notification_deliveries is a core system table containing delivery records
    # and must be preserved during rollback of the dose-grouping feature.
    op.execute("DROP TABLE IF EXISTS notification_dose_items CASCADE")
    op.execute("DROP INDEX IF EXISTS idx_notif_deliveries_recipient_scheduled")
