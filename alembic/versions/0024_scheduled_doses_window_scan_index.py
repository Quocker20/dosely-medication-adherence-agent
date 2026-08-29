"""scheduled_doses: index-only support for the nightly adherence-review scan

The nightly graded-severity review (Stage 3 of
docs/graded-adherence-implementation.md) computes six aggregates across every
patient in one GROUP BY patient_id pass per query -- deliberately not one
query per patient, to avoid N+1 at scan time. Those queries filter on a time
range with no patient_id predicate (they need every patient's doses in the
window at once), which idx_scheduled_doses_patient_time cannot serve: it
leads with patient_id, so a patient-agnostic range scan on that index still
means walking every patient's B-tree branch, degrading toward a sequential
scan as the table grows. Without a leading-column-first index for this access
pattern, scheduled_doses would be seq-scanned once a night, every night,
forever.

INCLUDE carries every column the six queries actually read (dose_slot for the
per-slot breakdown, medication_id for the per-medication breakdown,
is_critical for the severity bump, snooze_count/original_scheduled_at/
taken_at for lateness), so Postgres can answer them straight from the index
without a heap fetch per row.

Honest tradeoff: at today's data volume a nightly sequential scan would
likely still complete inside its time budget. This index is insurance for
next year's row count, not a fix for a problem observed today -- cheap to add
now, disruptive to add later under load.

Revision ID: 0024_dose_window_scan_idx
Revises: 0023_alerts_review_trigger
Create Date: 2026-08-29
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0024_dose_window_scan_idx"
down_revision: str | None = "0023_alerts_review_trigger"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute(
            "CREATE INDEX CONCURRENTLY idx_scheduled_doses_window_scan "
            "ON scheduled_doses (current_scheduled_at, patient_id, status) "
            "INCLUDE (dose_slot, medication_id, is_critical, snooze_count, "
            "original_scheduled_at, taken_at)"
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute(
            "DROP INDEX CONCURRENTLY IF EXISTS idx_scheduled_doses_window_scan"
        )
