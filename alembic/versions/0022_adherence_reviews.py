"""adherence_reviews: nightly graded-severity review history

Backs the "rules decide severity, LLM classifies cause" pipeline described in
docs/graded-adherence-response.md. One row per patient per night, written
ONLY when severity is not NONE -- storing a NONE row for every patient every
night would add ~365 rows/patient/year that are never read, since an
adherent patient generates no alert and no escalation state to track.

days_in_severity is written by the service as a running counter (carried
forward from the prior night's row, reset to 1 on any severity change or on
a gap in the review history), not recomputed by counting rows at read time --
that keeps a skipped nightly run degrade the escalation ladder rather than
corrupting it (see the docstring on AdherenceReviewService.resolve_action for
the exact rule).

uq_adherence_reviews_patient_date is not just an idempotency guard: it is the
primary defense against a double-fired nightly job creating two alerts for
one patient on one night. The service must INSERT this row before writing
any Alert/NotificationDelivery, so the second concurrent run's INSERT
collides here and aborts before it can write a duplicate downstream side
effect.

indicators freezes the exact numbers that produced `severity`, so an alert
can be reconstructed after the fact even once later dose actions change the
underlying scheduled_doses rows.

Revision ID: 0022_adherence_reviews
Revises: 0021_dose_is_critical
Create Date: 2026-08-29
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0022_adherence_reviews"
down_revision: str | None = "0021_dose_is_critical"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE adherence_reviews (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            patient_id UUID NOT NULL REFERENCES patient_profiles(user_id) ON DELETE CASCADE,
            review_date DATE NOT NULL,
            window_start DATE NOT NULL,
            window_end DATE NOT NULL,

            severity VARCHAR(20) NOT NULL,
            days_in_severity INTEGER NOT NULL DEFAULT 1,

            remedy_class VARCHAR(40),
            action_taken VARCHAR(30) NOT NULL,

            -- The numbers that produced `severity`, frozen for audit -- see
            -- module docstring.
            indicators JSONB NOT NULL DEFAULT '{}'::jsonb,

            llm_reasoning TEXT,
            llm_confidence VARCHAR(10),
            model_version VARCHAR(100),
            prompt_version VARCHAR(50),

            alert_id UUID REFERENCES alerts(id) ON DELETE SET NULL,
            notification_delivery_id UUID REFERENCES notification_deliveries(id) ON DELETE SET NULL,

            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )

    op.execute(
        "ALTER TABLE adherence_reviews ADD CONSTRAINT ck_adherence_reviews_severity "
        "CHECK (severity IN ('MILD','MODERATE','SEVERE')) NOT VALID"
    )
    op.execute(
        "ALTER TABLE adherence_reviews VALIDATE CONSTRAINT ck_adherence_reviews_severity"
    )

    op.execute(
        "ALTER TABLE adherence_reviews ADD CONSTRAINT ck_adherence_reviews_days "
        "CHECK (days_in_severity >= 1) NOT VALID"
    )
    op.execute(
        "ALTER TABLE adherence_reviews VALIDATE CONSTRAINT ck_adherence_reviews_days"
    )

    op.execute(
        "ALTER TABLE adherence_reviews ADD CONSTRAINT ck_adherence_reviews_remedy "
        "CHECK (remedy_class IS NULL OR remedy_class IN ("
        "'RESCHEDULE_TIMING','SUSPECTED_SIDE_EFFECT','DELIBERATE_REFUSAL',"
        "'DISENGAGEMENT','EXTERNAL_DISRUPTION','UNCLEAR')) NOT VALID"
    )
    op.execute(
        "ALTER TABLE adherence_reviews VALIDATE CONSTRAINT ck_adherence_reviews_remedy"
    )

    op.execute(
        "ALTER TABLE adherence_reviews ADD CONSTRAINT ck_adherence_reviews_action "
        "CHECK (action_taken IN ("
        "'NONE','PATIENT_NOTIFICATION','DOCTOR_WARNING','DOCTOR_ALERT')) NOT VALID"
    )
    op.execute(
        "ALTER TABLE adherence_reviews VALIDATE CONSTRAINT ck_adherence_reviews_action"
    )

    op.execute(
        "ALTER TABLE adherence_reviews ADD CONSTRAINT ck_adherence_reviews_confidence "
        "CHECK (llm_confidence IS NULL OR llm_confidence IN ('high','medium','low')) NOT VALID"
    )
    op.execute(
        "ALTER TABLE adherence_reviews VALIDATE CONSTRAINT ck_adherence_reviews_confidence"
    )

    with op.get_context().autocommit_block():
        # Idempotency guard AND the primary defense against a double-fired
        # nightly run writing two alerts for the same patient/night -- see
        # module docstring.
        op.execute(
            "CREATE UNIQUE INDEX CONCURRENTLY uq_adherence_reviews_patient_date "
            "ON adherence_reviews (patient_id, review_date)"
        )
        # Escalation lookup: "the most recent review for each of these
        # patients", fetched as one DISTINCT ON query for the whole nightly
        # batch rather than one query per patient.
        op.execute(
            "CREATE INDEX CONCURRENTLY idx_adherence_reviews_patient_date_desc "
            "ON adherence_reviews (patient_id, review_date DESC)"
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute(
            "DROP INDEX CONCURRENTLY IF EXISTS idx_adherence_reviews_patient_date_desc"
        )
        op.execute(
            "DROP INDEX CONCURRENTLY IF EXISTS uq_adherence_reviews_patient_date"
        )
    op.execute("DROP TABLE adherence_reviews")
