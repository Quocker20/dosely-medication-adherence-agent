"""routine_overrides: same-day and future-day routine override with status

Revision ID: 0029_routine_overrides
Revises: 0028_alerts_review_check_fix
Create Date: 2026-09-01
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0029_routine_overrides"
down_revision: str | None = "0028_alerts_review_check_fix"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS routine_overrides (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            patient_id UUID NOT NULL REFERENCES patient_profiles(user_id) ON DELETE CASCADE,
            override_date DATE NOT NULL,
            anchor VARCHAR(20) NOT NULL,
            overridden_time TIME NOT NULL,
            source VARCHAR(20) NOT NULL,
            reason TEXT,
            status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
            consumed_by_run_id UUID REFERENCES agent_runs(id) ON DELETE SET NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )

    op.execute("ALTER TABLE routine_overrides DROP CONSTRAINT IF EXISTS ck_routine_overrides_anchor")
    op.execute(
        "ALTER TABLE routine_overrides ADD CONSTRAINT ck_routine_overrides_anchor "
        "CHECK (anchor IN ('breakfast','lunch','dinner','sleep')) NOT VALID"
    )
    op.execute("ALTER TABLE routine_overrides VALIDATE CONSTRAINT ck_routine_overrides_anchor")

    op.execute("ALTER TABLE routine_overrides DROP CONSTRAINT IF EXISTS ck_routine_overrides_source")
    op.execute(
        "ALTER TABLE routine_overrides ADD CONSTRAINT ck_routine_overrides_source "
        "CHECK (source IN ('SURVEY','CHAT')) NOT VALID"
    )
    op.execute("ALTER TABLE routine_overrides VALIDATE CONSTRAINT ck_routine_overrides_source")

    op.execute("ALTER TABLE routine_overrides DROP CONSTRAINT IF EXISTS ck_routine_overrides_status")
    op.execute(
        "ALTER TABLE routine_overrides ADD CONSTRAINT ck_routine_overrides_status "
        "CHECK (status IN ('ACTIVE','REJECTED','CANCELLED')) NOT VALID"
    )
    op.execute("ALTER TABLE routine_overrides VALIDATE CONSTRAINT ck_routine_overrides_status")

    with op.get_context().autocommit_block():
        op.execute(
            "CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS uq_routine_overrides_patient_date_anchor "
            "ON routine_overrides (patient_id, override_date, anchor)"
        )

    # set_updated_at() defined in migration 0005.
    op.execute("DROP TRIGGER IF EXISTS trg_routine_overrides_set_updated_at ON routine_overrides")
    op.execute(
        "CREATE TRIGGER trg_routine_overrides_set_updated_at "
        "BEFORE UPDATE ON routine_overrides "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_routine_overrides_set_updated_at ON routine_overrides")
    with op.get_context().autocommit_block():
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS uq_routine_overrides_patient_date_anchor")
    op.execute("DROP TABLE IF EXISTS routine_overrides")
