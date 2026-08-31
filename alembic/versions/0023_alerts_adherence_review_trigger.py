"""alerts: add ADHERENCE_REVIEW to ck_alerts_triggered_by_type

The nightly graded-severity review (docs/graded-adherence-implementation.md
Stage 6) writes Alert rows for its DOCTOR_WARNING/DOCTOR_ALERT actions, using
triggered_by_type='ADHERENCE_REVIEW' to distinguish them on the doctor
dashboard from the three existing sources (SOS_BUTTON, SEVERE_SYMPTOM,
MISSED_DOSES). MISSED_DOSES is kept: historical rows carry it, and the
narrowed critical-only fast path (migration 0021 + the Stage 2 service
change) still writes it for a 3-consecutive-miss streak on a flagged
medication.

Same drop-and-recreate NOT VALID/VALIDATE two-step as the original
ck_alerts_triggered_by_type (migration 0009_slice7_adherence_alerts) --
VALIDATE only needs SHARE UPDATE EXCLUSIVE, so it does not block writers on
this table (which include the SOS/red-alert safety path) while re-scanning
existing rows.

Revision ID: 0023_alerts_review_trigger
Revises: 0022_adherence_reviews
Create Date: 2026-08-29
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0023_alerts_review_trigger"
down_revision: str | None = "0022_adherence_reviews"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE alerts DROP CONSTRAINT ck_alerts_triggered_by_type")
    op.execute(
        "ALTER TABLE alerts ADD CONSTRAINT ck_alerts_triggered_by_type "
        "CHECK (triggered_by_type IN "
        "('SOS_BUTTON','SEVERE_SYMPTOM','MISSED_DOSES','ADHERENCE_REVIEW')) NOT VALID"
    )
    op.execute("ALTER TABLE alerts VALIDATE CONSTRAINT ck_alerts_triggered_by_type")


def downgrade() -> None:
    op.execute("ALTER TABLE alerts DROP CONSTRAINT ck_alerts_triggered_by_type")
    op.execute(
        "ALTER TABLE alerts ADD CONSTRAINT ck_alerts_triggered_by_type "
        "CHECK (triggered_by_type IN "
        "('SOS_BUTTON','SEVERE_SYMPTOM','MISSED_DOSES')) NOT VALID"
    )
    op.execute("ALTER TABLE alerts VALIDATE CONSTRAINT ck_alerts_triggered_by_type")
