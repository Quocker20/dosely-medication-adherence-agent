"""slice5: prescription_items FK index, patient-scoped list index, status CHECK

Revision ID: 0006_slice5_idx
Revises: 0005_updated_at_trg
Create Date: 2026-08-13

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0006_slice5_idx"
down_revision: Union[str, None] = "0005_updated_at_trg"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # NOT VALID skips the full-table scan, so ADD CONSTRAINT only takes a brief
    # AccessExclusiveLock instead of holding it for the scan. VALIDATE CONSTRAINT
    # then does the scan under ShareUpdateExclusiveLock, which blocks neither
    # reads nor writes. Enforces the DRAFT/APPROVED/CANCELLED state machine at
    # the DB layer too, not just in the service.
    op.execute(
        "ALTER TABLE prescriptions ADD CONSTRAINT ck_prescriptions_status "
        "CHECK (status IN ('DRAFT','APPROVED','CANCELLED')) NOT VALID"
    )
    op.execute("ALTER TABLE prescriptions VALIDATE CONSTRAINT ck_prescriptions_status")

    # CONCURRENTLY takes ShareLock instead of the plain-CREATE-INDEX default of
    # ShareLock-blocking-writes-for-the-whole-build; it cannot run inside a
    # transaction, hence the autocommit_block.
    with op.get_context().autocommit_block():
        # Postgres never auto-indexes a FK column. Backs: fetching a
        # prescription's items (PrescriptionRepository.get_items), the batch
        # IN-clause fetch across many prescriptions on the list endpoint
        # (get_items_for_prescriptions), and ON DELETE CASCADE from
        # prescriptions — all a seq scan without this.
        op.execute(
            "CREATE INDEX CONCURRENTLY idx_prescription_items_prescription_id "
            "ON prescription_items (prescription_id)"
        )
        # GET /patients/{patient_id}/prescriptions filters on patient_id and
        # orders by created_at DESC with OFFSET/LIMIT. Without this the
        # planner sorts the whole per-patient set before it can discard all
        # but one page.
        op.execute(
            "CREATE INDEX CONCURRENTLY idx_prescriptions_patient_created "
            "ON prescriptions (patient_id, created_at DESC)"
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_prescriptions_patient_created")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_prescription_items_prescription_id")

    op.drop_constraint("ck_prescriptions_status", "prescriptions", type_="check")
