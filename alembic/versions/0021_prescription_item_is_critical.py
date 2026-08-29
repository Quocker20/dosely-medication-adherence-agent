"""is_critical: doctor-set flag on prescription_items, snapshotted onto scheduled_doses

Trigger 1 of the missed-dose safety scan currently pages a doctor for a
3-consecutive-miss streak on ANY medication -- a missed vitamin alerts
identically to a missed anticoagulant. This adds a per-item boolean a doctor
sets on high-risk medications, so the fast-path scan can be narrowed to only
those (see the follow-up service change in
docs/graded-adherence-implementation.md Stage 2).

prescription_items.is_critical is the doctor-editable source. scheduled_doses
gets its own is_critical column as an immutable generation-time snapshot --
same pattern as dose_slot/medication_id/dose_value from migration
0011_schedule_dose_snapshots -- rather than a join back to
prescription_items at query time. This is safe because items are only
editable while the prescription is DRAFT and doses are generated at
approve time, so the snapshot cannot drift from the item after the fact.

Both columns are NOT NULL DEFAULT FALSE. On Postgres 11+ this is
metadata-only (the default is recorded in the catalog, not backfilled row by
row), so neither ALTER TABLE rewrites the table or holds a long lock.

The partial index only covers flagged doses, so it stays proportional to
actual doctor usage rather than table size -- it starts near-empty, since the
column defaults to false for every existing row.

Revision ID: 0021_dose_is_critical
Revises: 0020_merge_heads
Create Date: 2026-08-29
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0021_dose_is_critical"
down_revision: str | None = "0020_merge_heads"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE prescription_items "
        "ADD COLUMN is_critical BOOLEAN NOT NULL DEFAULT FALSE"
    )
    op.execute(
        "ALTER TABLE scheduled_doses "
        "ADD COLUMN is_critical BOOLEAN NOT NULL DEFAULT FALSE"
    )

    # CONCURRENTLY cannot run inside a transaction block.
    with op.get_context().autocommit_block():
        # Backs the narrowed missed-dose-streak scan: fetch only the most
        # recent doses per patient that are flagged critical, newest first.
        op.execute(
            "CREATE INDEX CONCURRENTLY idx_scheduled_doses_critical_patient_time "
            "ON scheduled_doses (patient_id, current_scheduled_at DESC) "
            "WHERE is_critical"
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute(
            "DROP INDEX CONCURRENTLY IF EXISTS idx_scheduled_doses_critical_patient_time"
        )
    op.execute("ALTER TABLE scheduled_doses DROP COLUMN is_critical")
    op.execute("ALTER TABLE prescription_items DROP COLUMN is_critical")
