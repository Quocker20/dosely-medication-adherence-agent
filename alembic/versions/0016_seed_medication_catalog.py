"""Seed the starter relational medication catalog.

Revision ID: 0016_seed_medications
Revises: 0015_agent_run_claim
Create Date: 2026-08-24
"""

from collections.abc import Sequence
import json
from pathlib import Path

import sqlalchemy as sa
from alembic import op

revision: str = "0016_seed_medications"
down_revision: str | None = "0015_agent_run_claim"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SOURCE_NAME = "WHO_EML_2023_STARTER"
SOURCE_REF = "https://www.who.int/publications/i/item/WHO-MHP-HPS-EML-2023.02"


def _catalog() -> list[dict[str, str]]:
    path = Path(__file__).resolve().parents[2] / "scripts" / "data" / "who_eml_2023_starter.json"
    return json.loads(path.read_text(encoding="utf-8"))


def upgrade() -> None:
    statement = sa.text(
        """
        INSERT INTO medications (
            name, composition, source_name, source_ref, source_record_key, is_active
        ) VALUES (
            :name, :composition, :source_name, :source_ref, :source_record_key, TRUE
        )
        ON CONFLICT (source_name, source_record_key)
            WHERE source_record_key IS NOT NULL
        DO UPDATE SET
            name = EXCLUDED.name,
            composition = EXCLUDED.composition,
            source_ref = EXCLUDED.source_ref,
            is_active = TRUE
        """
    )
    rows = [
        {
            "name": row["name"],
            "composition": row["composition"],
            "source_name": SOURCE_NAME,
            "source_ref": SOURCE_REF,
            "source_record_key": row["key"],
        }
        for row in _catalog()
    ]
    op.get_bind().execute(statement, rows)


def downgrade() -> None:
    op.get_bind().execute(
        sa.text("DELETE FROM medications WHERE source_name = :source_name"),
        {"source_name": SOURCE_NAME},
    )
