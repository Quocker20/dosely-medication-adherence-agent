"""slice6: scheduled_doses/agent_runs indexes, CHECK constraints, updated_at trigger

scheduled_doses and agent_runs were created by the baseline init script with
zero indexes beyond their PK and zero CHECK constraints — this migration adds
what slice 6 (schedule generation/reschedule) needs to run without seq scans
or bad data, following the same NOT VALID/VALIDATE and CONCURRENTLY patterns
as migrations 0002/0006.

Revision ID: 0008_slice6_sched
Revises: 0007_drop_pi_med_fk
Create Date: 2026-08-13

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0008_slice6_sched"
down_revision: Union[str, None] = "0007_drop_pi_med_fk"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── scheduled_doses CHECK constraints ──
    op.execute(
        "ALTER TABLE scheduled_doses ADD CONSTRAINT ck_scheduled_doses_status "
        "CHECK (status IN ('PENDING','TAKEN','SKIPPED','MISSED')) NOT VALID"
    )
    op.execute("ALTER TABLE scheduled_doses VALIDATE CONSTRAINT ck_scheduled_doses_status")

    op.execute(
        "ALTER TABLE scheduled_doses ADD CONSTRAINT ck_scheduled_doses_snooze_count "
        "CHECK (snooze_count >= 0) NOT VALID"
    )
    op.execute(
        "ALTER TABLE scheduled_doses VALIDATE CONSTRAINT ck_scheduled_doses_snooze_count"
    )

    op.execute(
        "ALTER TABLE scheduled_doses ADD CONSTRAINT ck_scheduled_doses_taken_at "
        "CHECK (status <> 'TAKEN' OR taken_at IS NOT NULL) NOT VALID"
    )
    op.execute("ALTER TABLE scheduled_doses VALIDATE CONSTRAINT ck_scheduled_doses_taken_at")

    # ── agent_runs CHECK constraints ──
    op.execute(
        "ALTER TABLE agent_runs ADD CONSTRAINT ck_agent_runs_agent_type "
        "CHECK (agent_type IN ('PLANNING_AGENT','RESCHEDULING_AGENT')) NOT VALID"
    )
    op.execute("ALTER TABLE agent_runs VALIDATE CONSTRAINT ck_agent_runs_agent_type")

    op.execute(
        "ALTER TABLE agent_runs ADD CONSTRAINT ck_agent_runs_trigger_type "
        "CHECK (trigger_type IN ('PRESCRIPTION_APPROVED','ROUTINE_UPDATED','MANUAL')) NOT VALID"
    )
    op.execute("ALTER TABLE agent_runs VALIDATE CONSTRAINT ck_agent_runs_trigger_type")

    op.execute(
        "ALTER TABLE agent_runs ADD CONSTRAINT ck_agent_runs_status "
        "CHECK (status IN ('RUNNING','COMPLETED','FAILED')) NOT VALID"
    )
    op.execute("ALTER TABLE agent_runs VALIDATE CONSTRAINT ck_agent_runs_status")

    op.execute(
        "ALTER TABLE agent_runs ADD CONSTRAINT ck_agent_runs_latency "
        "CHECK (latency_ms IS NULL OR latency_ms >= 0) NOT VALID"
    )
    op.execute("ALTER TABLE agent_runs VALIDATE CONSTRAINT ck_agent_runs_latency")

    op.execute(
        "ALTER TABLE agent_runs ADD CONSTRAINT ck_agent_runs_dose_count "
        "CHECK (generated_dose_count IS NULL OR generated_dose_count >= 0) NOT VALID"
    )
    op.execute("ALTER TABLE agent_runs VALIDATE CONSTRAINT ck_agent_runs_dose_count")

    # ── updated_at trigger: Core update() writes (snooze, dose actions) never
    # invoke a Python-side onupdate=, same reason migration 0005 added the
    # trigger to patient_profiles/patient_routines. Reuses set_updated_at().
    op.execute(
        "CREATE TRIGGER trg_scheduled_doses_set_updated_at "
        "BEFORE UPDATE ON scheduled_doses "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )

    # ── CONCURRENTLY indexes: cannot run inside a transaction ──
    with op.get_context().autocommit_block():
        # Idempotency for schedule generation: a re-run (retry, duplicate
        # Celery delivery) can ON CONFLICT DO NOTHING per (item, original
        # time) instead of duplicating rows. Leading column also serves
        # ON DELETE CASCADE from prescription_items and item-scoped joins.
        op.execute(
            "CREATE UNIQUE INDEX CONCURRENTLY uq_scheduled_doses_item_original "
            "ON scheduled_doses (prescription_item_id, original_scheduled_at)"
        )
        # GET /patients/{id}/schedules?date=... filters patient + time range,
        # orders by time. Also backs the reschedule delete predicate
        # (patient_id, status='PENDING', current_scheduled_at > now) and
        # ON DELETE CASCADE from patient_profiles.
        op.execute(
            "CREATE INDEX CONCURRENTLY idx_scheduled_doses_patient_time "
            "ON scheduled_doses (patient_id, current_scheduled_at)"
        )
        # Partial index for the cross-patient "doses due soon" notification
        # scan — shrinks as doses leave PENDING instead of growing forever.
        op.execute(
            "CREATE INDEX CONCURRENTLY idx_scheduled_doses_pending_due "
            "ON scheduled_doses (current_scheduled_at) WHERE status = 'PENDING'"
        )

        # Latest-run-for-patient / dashboard history; ON DELETE CASCADE from
        # patient_profiles.
        op.execute(
            "CREATE INDEX CONCURRENTLY idx_agent_runs_patient_created "
            "ON agent_runs (patient_id, created_at DESC)"
        )
        # Postgres never auto-indexes a FK column; backs ON DELETE SET NULL
        # from prescriptions.
        op.execute(
            "CREATE INDEX CONCURRENTLY idx_agent_runs_prescription_id "
            "ON agent_runs (prescription_id)"
        )
        # Enforces one in-flight run per patient at the DB layer: a second
        # concurrent generate/reschedule call fails the INSERT with
        # IntegrityError, which the service turns into 409 Conflict, instead
        # of two agent runs racing to write the same schedule.
        op.execute(
            "CREATE UNIQUE INDEX CONCURRENTLY uq_agent_runs_one_running "
            "ON agent_runs (patient_id) WHERE status = 'RUNNING'"
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS uq_agent_runs_one_running")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_agent_runs_prescription_id")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_agent_runs_patient_created")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_scheduled_doses_pending_due")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_scheduled_doses_patient_time")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS uq_scheduled_doses_item_original")

    op.execute(
        "DROP TRIGGER IF EXISTS trg_scheduled_doses_set_updated_at ON scheduled_doses"
    )

    op.drop_constraint("ck_agent_runs_dose_count", "agent_runs", type_="check")
    op.drop_constraint("ck_agent_runs_latency", "agent_runs", type_="check")
    op.drop_constraint("ck_agent_runs_status", "agent_runs", type_="check")
    op.drop_constraint("ck_agent_runs_trigger_type", "agent_runs", type_="check")
    op.drop_constraint("ck_agent_runs_agent_type", "agent_runs", type_="check")

    op.drop_constraint("ck_scheduled_doses_taken_at", "scheduled_doses", type_="check")
    op.drop_constraint("ck_scheduled_doses_snooze_count", "scheduled_doses", type_="check")
    op.drop_constraint("ck_scheduled_doses_status", "scheduled_doses", type_="check")
