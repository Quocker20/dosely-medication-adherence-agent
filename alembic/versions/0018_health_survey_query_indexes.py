"""health_surveys: dedupe existing rows, UNIQUE(patient_id, survey_date), doctor-scoped list indexes

New doctor-facing GET /health-surveys (list all + per-patient) needs a UNIQUE
constraint to close the double-submit race in HealthSurveyService.submit_health_survey
(check-then-insert at the service layer was never atomic), plus query indexes
so the platform-wide list doesn't seq-scan/sort and a severity filter doesn't
scan symptom_reports.

Before the constraint can be added, any pre-existing duplicate
(patient_id, survey_date) rows must be collapsed to one. This is destructive:
duplicate health_surveys rows are permanently deleted (keeping the newest by
submitted_at/created_at/id), and any symptom_reports pointing at a deleted
duplicate are re-pointed to the kept row first so they are not orphaned to
NULL by the FK's ON DELETE SET NULL. downgrade() cannot restore the deleted
duplicates.

Revision ID: 0018_health_survey_query_indexes
Revises: 0017_agent_run_error_message
Create Date: 2026-08-26
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0018_health_survey_query_indexes"
down_revision: str | None = "0017_agent_run_error_message"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── dedupe: keep one row per (patient_id, survey_date), newest first ──
    op.execute(
        """
        CREATE TEMP TABLE _hs_survey_rank AS
        SELECT
            id,
            patient_id,
            survey_date,
            ROW_NUMBER() OVER (
                PARTITION BY patient_id, survey_date
                ORDER BY submitted_at DESC NULLS LAST, created_at DESC, id DESC
            ) AS rn
        FROM health_surveys
        """
    )
    op.execute(
        """
        CREATE TEMP TABLE _hs_survey_keep AS
        SELECT
            dup.id AS dup_id,
            keep.id AS keep_id
        FROM _hs_survey_rank dup
        JOIN _hs_survey_rank keep
            ON keep.patient_id = dup.patient_id
            AND keep.survey_date = dup.survey_date
            AND keep.rn = 1
        WHERE dup.rn > 1
        """
    )
    # Re-point symptom_reports off the rows about to be deleted so they stay
    # attached to the surviving survey instead of falling to SET NULL.
    op.execute(
        """
        UPDATE symptom_reports sr
        SET survey_id = k.keep_id
        FROM _hs_survey_keep k
        WHERE sr.survey_id = k.dup_id
        """
    )
    op.execute(
        """
        DELETE FROM health_surveys hs
        USING _hs_survey_keep k
        WHERE hs.id = k.dup_id
        """
    )
    op.execute("DROP TABLE _hs_survey_keep")
    op.execute("DROP TABLE _hs_survey_rank")

    # ── UNIQUE constraint: closes the double-submit race at the DB layer ──
    op.execute(
        "ALTER TABLE health_surveys ADD CONSTRAINT uq_health_surveys_patient_date "
        "UNIQUE (patient_id, survey_date)"
    )

    # ── CONCURRENTLY indexes: cannot run inside a transaction ──
    with op.get_context().autocommit_block():
        # GET /health-surveys (DOCTOR/ADMIN, platform-wide) filters survey_date
        # range and orders newest-first; (patient_id, survey_date DESC) from
        # migration 0009 doesn't help an unscoped list. id DESC breaks ties so
        # pagination stays stable across pages.
        op.execute(
            "CREATE INDEX CONCURRENTLY idx_health_surveys_date_id "
            "ON health_surveys (survey_date DESC, id DESC)"
        )
        # GET /health-surveys?severity= semi-joins symptom_reports by severity;
        # without this it's a seq scan over the whole table.
        op.execute(
            "CREATE INDEX CONCURRENTLY idx_symptom_reports_severity_survey "
            "ON symptom_reports (severity, survey_id)"
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute(
            "DROP INDEX CONCURRENTLY IF EXISTS idx_symptom_reports_severity_survey"
        )
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_health_surveys_date_id")

    op.execute(
        "ALTER TABLE health_surveys DROP CONSTRAINT IF EXISTS uq_health_surveys_patient_date"
    )
    # Deduped rows deleted by upgrade() are not restored.
