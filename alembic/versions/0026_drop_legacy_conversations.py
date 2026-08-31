"""drop legacy generic conversation tables

Revision ID: 0026_drop_legacy_conversations
Revises: 0025_merge_chat_adherence
Create Date: 2026-08-31
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0026_drop_legacy_conversations"
down_revision: str | tuple[str, ...] | None = "0025_merge_chat_adherence"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("DROP TABLE IF EXISTS messages")
    op.execute("DROP TABLE IF EXISTS conversations")


def downgrade() -> None:
    op.execute(
        """
        CREATE TABLE conversations (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            patient_id UUID,
            title VARCHAR(255),
            status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
            last_message_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE messages (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            conversation_id UUID,
            role VARCHAR(20) NOT NULL,
            provider VARCHAR(50),
            model_name VARCHAR(100),
            input_tokens INTEGER,
            output_tokens INTEGER,
            cost_amount NUMERIC(12,6),
            content TEXT NOT NULL,
            currency VARCHAR(10) DEFAULT 'USD',
            latency_ms INTEGER,
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
