"""slice7: adherence_logs/health_surveys/symptom_reports/alerts CHECK constraints, indexes, updated_at trigger

Baseline init script created these four tables with zero indexes beyond PK/FK
and zero CHECK constraints — this migration adds what slice 7 (adherence
logging, health surveys, SOS/safety alerts) needs to run without seq scans or
bad data, following the same NOT VALID/VALIDATE and CONCURRENTLY patterns as
migrations 0002/0006/0008.

Revision ID: 0009_slice7_adherence
Revises: 0008_slice6_sched
Create Date: 2026-08-13

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0009_slice7_adherence"
down_revision: Union[str, None] = "0008_slice6_sched"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── adherence_logs CHECK constraints ──
    op.execute(
        "ALTER TABLE adherence_logs ADD CONSTRAINT ck_adherence_logs_action "
        "CHECK (action IN ('TAKEN','SNOOZE','SKIPPED')) NOT VALID"
    )
    op.execute("ALTER TABLE adherence_logs VALIDATE CONSTRAINT ck_adherence_logs_action")

    # ── symptom_reports CHECK constraints ──
    op.execute(
        "ALTER TABLE symptom_reports ADD CONSTRAINT ck_symptom_reports_severity "
        "CHECK (severity IN ('MILD','MODERATE','SEVERE')) NOT VALID"
    )
    op.execute(
        "ALTER TABLE symptom_reports VALIDATE CONSTRAINT ck_symptom_reports_severity"
    )

    # ── alerts CHECK constraints ──
    op.execute(
        "ALTER TABLE alerts ADD CONSTRAINT ck_alerts_triggered_by_type "
        "CHECK (triggered_by_type IN ('SOS_BUTTON','SEVERE_SYMPTOM','MISSED_DOSES')) NOT VALID"
    )
    op.execute(
        "ALTER TABLE alerts VALIDATE CONSTRAINT ck_alerts_triggered_by_type"
    )

    op.execute(
        "ALTER TABLE alerts ADD CONSTRAINT ck_alerts_alert_type "
        "CHECK (alert_type IN ('RED_ALERT','WARNING')) NOT VALID"
    )
    op.execute("ALTER TABLE alerts VALIDATE CONSTRAINT ck_alerts_alert_type")

    op.execute(
        "ALTER TABLE alerts ADD CONSTRAINT ck_alerts_severity "
        "CHECK (severity IN ('CRITICAL','HIGH','MEDIUM')) NOT VALID"
    )
    op.execute("ALTER TABLE alerts VALIDATE CONSTRAINT ck_alerts_severity")

    op.execute(
        "ALTER TABLE alerts ADD CONSTRAINT ck_alerts_status "
        "CHECK (status IN ('OPEN','ACKNOWLEDGED','RESOLVED')) NOT VALID"
    )
    op.execute("ALTER TABLE alerts VALIDATE CONSTRAINT ck_alerts_status")

    # ── updated_at trigger: acknowledge/resolve are Core update() writes,
    # which never invoke a Python-side onupdate=, same reason migration 0005/
    # 0008 attached it to patient_profiles/scheduled_doses. Reuses
    # set_updated_at() defined in the baseline init script.
    op.execute(
        "CREATE TRIGGER trg_alerts_set_updated_at "
        "BEFORE UPDATE ON alerts "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )

    # ── CONCURRENTLY indexes: cannot run inside a transaction ──
    with op.get_context().autocommit_block():
        # Postgres never auto-indexes a FK column. Backs ON DELETE CASCADE
        # from scheduled_doses when a dose row is purged.
        op.execute(
            "CREATE INDEX CONCURRENTLY idx_adherence_logs_scheduled_dose_id "
            "ON adherence_logs (scheduled_dose_id)"
        )
        # GET /patients/{patient_id}/adherence(/logs)?from&to filters patient_id
        # + performed_at range, orders by performed_at DESC. Also backs
        # ON DELETE CASCADE from patient_profiles.
        op.execute(
            "CREATE INDEX CONCURRENTLY idx_adherence_logs_patient_performed "
            "ON adherence_logs (patient_id, performed_at DESC)"
        )

        # Dashboard's last_survey_date (DashboardPatientListResponse) needs
        # MAX(survey_date) per patient; also backs ON DELETE CASCADE from
        # patient_profiles.
        op.execute(
            "CREATE INDEX CONCURRENTLY idx_health_surveys_patient_date "
            "ON health_surveys (patient_id, survey_date DESC)"
        )

        # Postgres never auto-indexes a FK column. Backs ON DELETE CASCADE
        # from patient_profiles and per-patient symptom history lookups.
        op.execute(
            "CREATE INDEX CONCURRENTLY idx_symptom_reports_patient_reported "
            "ON symptom_reports (patient_id, reported_at DESC)"
        )
        # Backs ON DELETE SET NULL from health_surveys (fetching a survey's
        # symptom_reports).
        op.execute(
            "CREATE INDEX CONCURRENTLY idx_symptom_reports_survey_id "
            "ON symptom_reports (survey_id)"
        )

        # GET /patients/{patient_id}/sos and cascade delete from
        # patient_profiles.
        op.execute(
            "CREATE INDEX CONCURRENTLY idx_alerts_patient_created "
            "ON alerts (patient_id, created_at DESC)"
        )
        # GET /alerts?status=&patientId= doctor dashboard list, ordered by
        # recency.
        op.execute(
            "CREATE INDEX CONCURRENTLY idx_alerts_status_created "
            "ON alerts (status, created_at DESC)"
        )
        # Postgres never auto-indexes a FK column; backs ON DELETE SET NULL
        # from doctor_profiles.
        op.execute(
            "CREATE INDEX CONCURRENTLY idx_alerts_assigned_doctor_id "
            "ON alerts (assigned_doctor_id)"
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_alerts_assigned_doctor_id")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_alerts_status_created")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_alerts_patient_created")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_symptom_reports_survey_id")
        op.execute(
            "DROP INDEX CONCURRENTLY IF EXISTS idx_symptom_reports_patient_reported"
        )
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_health_surveys_patient_date")
        op.execute(
            "DROP INDEX CONCURRENTLY IF EXISTS idx_adherence_logs_patient_performed"
        )
        op.execute(
            "DROP INDEX CONCURRENTLY IF EXISTS idx_adherence_logs_scheduled_dose_id"
        )

    op.execute("DROP TRIGGER IF EXISTS trg_alerts_set_updated_at ON alerts")

    op.drop_constraint("ck_alerts_status", "alerts", type_="check")
    op.drop_constraint("ck_alerts_severity", "alerts", type_="check")
    op.drop_constraint("ck_alerts_alert_type", "alerts", type_="check")
    op.drop_constraint("ck_alerts_triggered_by_type", "alerts", type_="check")

    op.drop_constraint("ck_symptom_reports_severity", "symptom_reports", type_="check")

    op.drop_constraint("ck_adherence_logs_action", "adherence_logs", type_="check")
