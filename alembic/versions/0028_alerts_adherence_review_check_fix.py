"""alerts: restore ADHERENCE_REVIEW to ck_alerts_triggered_by_type

0021_suspected_adverse_events and 0023_alerts_review_trigger are sibling
branches that both drop and recreate ck_alerts_triggered_by_type with
mutually exclusive value sets -- 0021 adds ADVERSE_EVENT, 0023 adds
ADHERENCE_REVIEW, and neither depends on the other. They meet only at
0026_seed_curated_products, whose down_revision is
(0021_suspected_adverse_events, 0025_merge_chat_adherence). Whichever branch
Alembic walked last silently won; on this deployment that was 0021.

Confirmed against production (docs/adherence-review-fix-plan.md Defect 2):

    SELECT conname, pg_get_constraintdef(oid)
    FROM pg_constraint WHERE conname LIKE 'ck_alerts%';

    ck_alerts_triggered_by_type: SOS_BUTTON, SEVERE_SYMPTOM, MISSED_DOSES,
    ADVERSE_EVENT   -- ADHERENCE_REVIEW is missing.

Without ADHERENCE_REVIEW, every DOCTOR_WARNING/DOCTOR_ALERT the nightly
graded-adherence review writes (src/modules/adherence_review/service.py,
_persist_one) violates this CHECK constraint. This revision writes the union
of both branches' value sets so neither write path is broken again.

Revision ID: 0028_alerts_review_check_fix
Revises: 0027_merge_catalog_legacy
Create Date: 2026-08-31
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0028_alerts_review_check_fix"
down_revision: str | None = "0027_merge_catalog_legacy"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE alerts DROP CONSTRAINT ck_alerts_triggered_by_type")
    op.execute(
        "ALTER TABLE alerts ADD CONSTRAINT ck_alerts_triggered_by_type "
        "CHECK (triggered_by_type IN ("
        "'SOS_BUTTON','SEVERE_SYMPTOM','MISSED_DOSES','ADVERSE_EVENT','ADHERENCE_REVIEW'"
        ")) NOT VALID"
    )
    op.execute("ALTER TABLE alerts VALIDATE CONSTRAINT ck_alerts_triggered_by_type")


def downgrade() -> None:
    # Restores exactly the set confirmed in production before this revision
    # (see module docstring), not an earlier revision's set -- a downgrade
    # must be reversible against the state it was actually applied to.
    op.execute("ALTER TABLE alerts DROP CONSTRAINT ck_alerts_triggered_by_type")
    op.execute(
        "ALTER TABLE alerts ADD CONSTRAINT ck_alerts_triggered_by_type "
        "CHECK (triggered_by_type IN ("
        "'SOS_BUTTON','SEVERE_SYMPTOM','MISSED_DOSES','ADVERSE_EVENT'"
        ")) NOT VALID"
    )
    op.execute("ALTER TABLE alerts VALIDATE CONSTRAINT ck_alerts_triggered_by_type")
