"""slice7: alerts.idempotency_key column + unique index

POST /patients/{patient_id}/sos requires an Idempotency-Key header
(api-contract.md) so a retried/duplicate-delivered SOS tap does not page a
doctor with two CRITICAL alerts. The alerts table (baseline init script) has
no column to store it, unlike adherence_logs/notification_deliveries which
already carry one — this migration adds the same pattern to alerts.

Revision ID: 0010_slice7_alert_idem
Revises: 0009_slice7_adherence
Create Date: 2026-08-13

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0010_slice7_alert_idem"
down_revision: Union[str, None] = "0009_slice7_adherence"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Plain ADD COLUMN (nullable, no default) is a metadata-only change on
    # Postgres 11+ — no table rewrite, near-instant regardless of row count.
    op.execute("ALTER TABLE alerts ADD COLUMN idempotency_key VARCHAR(100)")

    # Build the supporting unique index CONCURRENTLY (cannot run inside a
    # transaction) so it doesn't hold a write-blocking lock while it scans
    # the existing table.
    with op.get_context().autocommit_block():
        op.execute(
            "CREATE UNIQUE INDEX CONCURRENTLY uq_alerts_idempotency_key "
            "ON alerts (idempotency_key)"
        )

    # Multiple NULLs are allowed under a UNIQUE constraint (NULL <> NULL), so
    # only actual duplicate keys are rejected. ADD CONSTRAINT ... UNIQUE USING
    # INDEX attaches the already-built index instantly, no second scan.
    op.execute(
        "ALTER TABLE alerts ADD CONSTRAINT uq_alerts_idempotency_key "
        "UNIQUE USING INDEX uq_alerts_idempotency_key"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE alerts DROP CONSTRAINT IF EXISTS uq_alerts_idempotency_key")
    op.execute("ALTER TABLE alerts DROP COLUMN IF EXISTS idempotency_key")
