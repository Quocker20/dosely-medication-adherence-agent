"""Allow deterministic planning conflicts to finish as NEEDS_REVIEW.

Revision ID: 0012_agent_review
Revises: 0011_schedule_snapshots
Create Date: 2026-08-20
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0012_agent_review"
down_revision: str | None = "0011_schedule_snapshots"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Name varies by how this DB's schema was provisioned: DBs bootstrapped
    # straight from docs/database_v1_init.sql carry Postgres's default name
    # (agent_runs_status_check, unnamed inline CHECK) instead of the
    # ck_agent_runs_status name migration 0008 gives it when run for real.
    op.execute(
        "DO $$\n"
        "DECLARE cname text;\n"
        "BEGIN\n"
        "    SELECT conname INTO cname FROM pg_constraint\n"
        "    WHERE conrelid = 'agent_runs'::regclass AND contype = 'c'\n"
        "      AND pg_get_constraintdef(oid) LIKE '%status%RUNNING%';\n"
        "    IF cname IS NOT NULL THEN\n"
        "        EXECUTE format('ALTER TABLE agent_runs DROP CONSTRAINT %I', cname);\n"
        "    END IF;\n"
        "END $$;"
    )
    op.execute(
        "ALTER TABLE agent_runs ADD CONSTRAINT ck_agent_runs_status "
        "CHECK (status IN ('RUNNING','COMPLETED','FAILED','NEEDS_REVIEW')) NOT VALID"
    )
    op.execute("ALTER TABLE agent_runs VALIDATE CONSTRAINT ck_agent_runs_status")


def downgrade() -> None:
    # A downgrade cannot retain rows using a state unsupported by 0008.
    op.execute(
        "UPDATE agent_runs SET status = 'FAILED', "
        "error_code = COALESCE(error_code, 'NeedsReviewDowngrade') "
        "WHERE status = 'NEEDS_REVIEW'"
    )
    op.drop_constraint("ck_agent_runs_status", "agent_runs", type_="check")
    op.execute(
        "ALTER TABLE agent_runs ADD CONSTRAINT ck_agent_runs_status "
        "CHECK (status IN ('RUNNING','COMPLETED','FAILED')) NOT VALID"
    )
    op.execute("ALTER TABLE agent_runs VALIDATE CONSTRAINT ck_agent_runs_status")
