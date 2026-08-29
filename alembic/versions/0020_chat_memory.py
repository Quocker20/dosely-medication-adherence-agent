"""patient-scoped durable chat memory

Revision ID: 0020_chat_memory
Revises: 0019_user_need_onboarding
"""
from alembic import op

revision = "0020_chat_memory"
down_revision = ("0019_user_need_onboarding", "0016_seed_medications")
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE chat_conversations (
      id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
      patient_id UUID NOT NULL REFERENCES patient_profiles(user_id) ON DELETE CASCADE,
      summary TEXT,
      created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    CREATE INDEX ix_chat_conversations_patient_id ON chat_conversations(patient_id);
    CREATE TABLE chat_messages (
      id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
      conversation_id UUID NOT NULL REFERENCES chat_conversations(id) ON DELETE CASCADE,
      role VARCHAR(20) NOT NULL CHECK (role IN ('user','assistant')),
      content TEXT NOT NULL,
      intent VARCHAR(50),
      created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    CREATE INDEX ix_chat_messages_conversation_id ON chat_messages(conversation_id);
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS chat_messages")
    op.execute("DROP TABLE IF EXISTS chat_conversations")
