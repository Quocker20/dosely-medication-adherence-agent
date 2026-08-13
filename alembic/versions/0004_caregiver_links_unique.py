"""slice4: unique constraint on caregiver_links(patient_id, caregiver_user_id)

Revision ID: 0004_caregiver_uq
Revises: 0003_access_idx
Create Date: 2026-08-12

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0004_caregiver_uq"
down_revision: Union[str, None] = "0003_access_idx"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Build the unique index CONCURRENTLY first (no write-blocking ShareLock),
    # then attach it as a constraint — a metadata-only op that takes no scan.
    # This composite also serves list-by-patient reads: patient_id is the
    # leading column, so that query rides the same index for free.
    with op.get_context().autocommit_block():
        op.execute(
            "CREATE UNIQUE INDEX CONCURRENTLY uq_caregiver_links_patient_caregiver "
            "ON caregiver_links (patient_id, caregiver_user_id)"
        )
    op.execute(
        "ALTER TABLE caregiver_links ADD CONSTRAINT "
        "uq_caregiver_links_patient_caregiver UNIQUE USING INDEX "
        "uq_caregiver_links_patient_caregiver"
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_caregiver_links_patient_caregiver", "caregiver_links", type_="unique"
    )
