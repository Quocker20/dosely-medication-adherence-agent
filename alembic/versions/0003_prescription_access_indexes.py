"""slice3: indexes backing prescription-derived patient access

Revision ID: 0003_access_idx
Revises: 0002_slice3
Create Date: 2026-08-12

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003_access_idx"
down_revision: Union[str, None] = "0002_slice3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # CONCURRENTLY cannot run inside a transaction, hence the autocommit_block.
    with op.get_context().autocommit_block():
        # Both roster listing and single-patient fetch resolve access through
        # EXISTS (doctor_id = ? AND patient_id = ?). Carrying patient_id in the
        # index turns that probe into an index-only scan — no heap fetch at all.
        op.execute(
            "CREATE INDEX CONCURRENTLY idx_prescriptions_doctor_patient "
            "ON prescriptions (doctor_id, patient_id)"
        )
        # list_patients orders by created_at DESC with OFFSET/LIMIT. Without an
        # index the planner sorts the whole filtered set before it can discard
        # all but one page; worst on the unscoped ADMIN path where nothing
        # narrows the input first.
        op.execute(
            "CREATE INDEX CONCURRENTLY idx_patient_profiles_created_at "
            "ON patient_profiles (created_at DESC)"
        )
        # idx_prescriptions_doctor_id (from database_v1_init.sql) is a strict
        # leading-column prefix of the new composite, so every plan that used it
        # can use the composite instead. Keeping both only doubles write cost.
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_prescriptions_doctor_id")


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute(
            "CREATE INDEX CONCURRENTLY idx_prescriptions_doctor_id "
            "ON prescriptions (doctor_id)"
        )
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_patient_profiles_created_at")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_prescriptions_doctor_patient")
