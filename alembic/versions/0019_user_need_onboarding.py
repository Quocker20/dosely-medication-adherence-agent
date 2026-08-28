"""users: rename is_first_login to need_onboarding, add password_changed_at

is_first_login conflated two independent gates behind one boolean: "temp PIN
never changed" (all roles, security) and "patient never completed onboarding"
(PATIENT only, UX). A patient who changed their PIN but closed the app before
finishing the routine-onboarding screen had no way to be routed back to it on
relaunch, because the only flag available flipped false at PIN-change time.

need_onboarding keeps the column but repurposes the trigger: it now only
clears when a PATIENT actually finishes onboarding (POST /patients/me/profile
or a non-empty PUT /patients/{id}/routine), not on password change.

password_changed_at replaces the "must change temp PIN" half of the old
semantic (derived as password_changed_at IS NULL) so the two facts no longer
share storage. It is nullable with no default -- ADD COLUMN is metadata-only
in Postgres, no table rewrite.

Revision ID: 0019_user_need_onboarding
Revises: 0018_health_survey_query_indexes
Create Date: 2026-08-28
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0019_user_need_onboarding"
down_revision: str | None = "0018_health_survey_query_indexes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE users RENAME COLUMN is_first_login TO need_onboarding")
    op.execute("ALTER TABLE users ADD COLUMN password_changed_at TIMESTAMPTZ")
    # Backfill: anyone already past the old is_first_login gate already changed
    # their PIN. updated_at is the closest available proxy for when -- only
    # the IS NULL / NOT NULL distinction is load-bearing going forward, the
    # exact timestamp is advisory.
    op.execute(
        "UPDATE users SET password_changed_at = updated_at WHERE need_onboarding = FALSE"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE users DROP COLUMN password_changed_at")
    op.execute("ALTER TABLE users RENAME COLUMN need_onboarding TO is_first_login")
