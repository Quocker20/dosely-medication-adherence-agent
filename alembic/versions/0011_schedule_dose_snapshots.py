"""schedule dose snapshots for exact patient-facing dose details

The schedule previously retained only prescription_item_id and timestamps.
That was insufficient to tell which of an item's morning/noon/evening/bedtime
amounts produced a concrete row after the planner adjusted its time.  Store
the selected slot and its prescription values at generation time so clients
never have to guess a dose from display_name.

All columns are nullable for rows generated before this migration.  Those
legacy rows intentionally remain unknown instead of being backfilled from the
current prescription item, which could assign the wrong slot-specific amount.

Revision ID: 0011_schedule_snapshots
Revises: 0010_slice7_alert_idem
Create Date: 2026-08-14

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0011_schedule_snapshots"
down_revision: Union[str, None] = "0010_slice7_alert_idem"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE scheduled_doses ADD COLUMN dose_slot VARCHAR(20)")
    # prescription_items.medication_id deliberately has no FK to the catalog;
    # keep the immutable schedule snapshot equally tolerant of catalog churn.
    op.execute("ALTER TABLE scheduled_doses ADD COLUMN medication_id UUID")
    op.execute("ALTER TABLE scheduled_doses ADD COLUMN dose_value NUMERIC(10,3)")
    op.execute("ALTER TABLE scheduled_doses ADD COLUMN dose_unit VARCHAR(30)")
    op.execute("ALTER TABLE scheduled_doses ADD COLUMN meal_relation VARCHAR(30)")

    op.execute(
        "ALTER TABLE scheduled_doses ADD CONSTRAINT ck_scheduled_doses_dose_slot "
        "CHECK (dose_slot IS NULL OR dose_slot IN "
        "('MORNING','NOON','EVENING','BEDTIME')) NOT VALID"
    )
    op.execute(
        "ALTER TABLE scheduled_doses VALIDATE CONSTRAINT "
        "ck_scheduled_doses_dose_slot"
    )
    op.execute(
        "ALTER TABLE scheduled_doses ADD CONSTRAINT ck_scheduled_doses_dose_value "
        "CHECK (dose_value IS NULL OR dose_value > 0) NOT VALID"
    )
    op.execute(
        "ALTER TABLE scheduled_doses VALIDATE CONSTRAINT "
        "ck_scheduled_doses_dose_value"
    )
    op.execute(
        "ALTER TABLE scheduled_doses ADD CONSTRAINT ck_scheduled_doses_meal_relation "
        "CHECK (meal_relation IS NULL OR meal_relation IN "
        "('BEFORE_MEAL','AFTER_MEAL','WITH_MEAL')) NOT VALID"
    )
    op.execute(
        "ALTER TABLE scheduled_doses VALIDATE CONSTRAINT "
        "ck_scheduled_doses_meal_relation"
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_scheduled_doses_meal_relation", "scheduled_doses", type_="check"
    )
    op.drop_constraint(
        "ck_scheduled_doses_dose_value", "scheduled_doses", type_="check"
    )
    op.drop_constraint(
        "ck_scheduled_doses_dose_slot", "scheduled_doses", type_="check"
    )
    op.drop_column("scheduled_doses", "meal_relation")
    op.drop_column("scheduled_doses", "dose_unit")
    op.drop_column("scheduled_doses", "dose_value")
    op.drop_column("scheduled_doses", "medication_id")
    op.drop_column("scheduled_doses", "dose_slot")
