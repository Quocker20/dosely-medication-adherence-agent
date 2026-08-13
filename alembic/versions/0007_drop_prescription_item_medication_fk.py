"""slice5: drop prescription_items.medication_id FK (display_name now a frozen snapshot)

Revision ID: 0007_drop_pi_med_fk
Revises: 0006_slice5_idx
Create Date: 2026-08-13

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0007_drop_pi_med_fk"
down_revision: Union[str, None] = "0006_slice5_idx"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # display_name is now resolved from Medication.name and frozen onto the
    # row at write time (service._snapshot_item_fields) instead of being
    # doctor-typed. The FK is dropped so later edits/deletes of a medications
    # row never touch already-written prescription_items — medication_id
    # becomes a plain historical pointer, no referential enforcement.
    op.drop_constraint(
        "prescription_items_medication_id_fkey",
        "prescription_items",
        type_="foreignkey",
    )


def downgrade() -> None:
    op.create_foreign_key(
        "prescription_items_medication_id_fkey",
        "prescription_items",
        "medications",
        ["medication_id"],
        ["id"],
        ondelete="SET NULL",
    )
