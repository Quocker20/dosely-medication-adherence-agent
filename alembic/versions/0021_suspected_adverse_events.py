"""Add suspected adverse events captured from patient chat.

Revision ID: 0021_suspected_adverse_events
Revises: 0020_chat_memory
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0021_suspected_adverse_events"
down_revision = "0020_chat_memory"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("ck_alerts_triggered_by_type", "alerts", type_="check")
    op.drop_constraint("ck_alerts_alert_type", "alerts", type_="check")
    op.create_check_constraint("ck_alerts_triggered_by_type", "alerts", "triggered_by_type IN ('SOS_BUTTON','SEVERE_SYMPTOM','MISSED_DOSES','ADVERSE_EVENT')")
    op.create_check_constraint("ck_alerts_alert_type", "alerts", "alert_type IN ('RED_ALERT','WARNING','SUSPECTED_ADVERSE_EVENT')")
    op.create_table(
        "suspected_adverse_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("patient_profiles.user_id", ondelete="CASCADE"), nullable=False),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column("symptoms", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("related_medications", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("risk_level", sa.String(20), nullable=False),
        sa.Column("causality", sa.String(30), nullable=False, server_default="UNASSESSED"),
        sa.Column("review_status", sa.String(30), nullable=False, server_default="NEW"),
        sa.Column("source", sa.String(20), nullable=False, server_default="CHAT"),
        sa.Column("alert_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("alerts.id", ondelete="SET NULL"), nullable=True),
        sa.Column("clinician_note", sa.Text(), nullable=True),
        sa.Column("reported_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("doctor_profiles.user_id", ondelete="SET NULL"), nullable=True),
        sa.Column("daily_notified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.CheckConstraint("risk_level IN ('LOW','MODERATE','HIGH','CRITICAL')", name="ck_adverse_event_risk"),
        sa.CheckConstraint("causality IN ('UNASSESSED','POSSIBLE','UNLIKELY','CONFIRMED')", name="ck_adverse_event_causality"),
        sa.CheckConstraint("review_status IN ('NEW','ACKNOWLEDGED','REVIEWED')", name="ck_adverse_event_review_status"),
    )
    op.create_index("idx_adverse_events_patient_reported", "suspected_adverse_events", ["patient_id", sa.text("reported_at DESC")])
    op.create_index("idx_adverse_events_review_risk", "suspected_adverse_events", ["review_status", "risk_level", sa.text("reported_at DESC")])


def downgrade() -> None:
    op.drop_index("idx_adverse_events_review_risk", table_name="suspected_adverse_events")
    op.drop_index("idx_adverse_events_patient_reported", table_name="suspected_adverse_events")
    op.drop_table("suspected_adverse_events")
    op.drop_constraint("ck_alerts_alert_type", "alerts", type_="check")
    op.drop_constraint("ck_alerts_triggered_by_type", "alerts", type_="check")
    op.create_check_constraint("ck_alerts_triggered_by_type", "alerts", "triggered_by_type IN ('SOS_BUTTON','SEVERE_SYMPTOM','MISSED_DOSES')")
    op.create_check_constraint("ck_alerts_alert_type", "alerts", "alert_type IN ('RED_ALERT','WARNING')")
