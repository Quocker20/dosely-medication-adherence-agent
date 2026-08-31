"""Seed verified brand-to-ingredient catalog records.

Revision ID: 0026_seed_curated_products
Revises: 0021_suspected_adverse_events, 0025_merge_chat_adherence
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0026_seed_curated_products"
down_revision: str | tuple[str, ...] | None = (
    "0021_suspected_adverse_events",
    "0025_merge_chat_adherence",
)
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SOURCE_NAME = "PRODUCT_CATALOG_CURATED"


def upgrade() -> None:
    op.get_bind().execute(
        sa.text(
            """
            INSERT INTO medications (
                name, composition, manufacturer, uses, source_name, source_ref,
                source_record_key, is_active
            ) VALUES (
                :name, :composition, :manufacturer, :uses, :source_name,
                :source_ref, :source_record_key, TRUE
            )
            ON CONFLICT (source_name, source_record_key)
                WHERE source_record_key IS NOT NULL
            DO UPDATE SET
                name = EXCLUDED.name,
                composition = EXCLUDED.composition,
                manufacturer = EXCLUDED.manufacturer,
                uses = EXCLUDED.uses,
                source_ref = EXCLUDED.source_ref,
                is_active = TRUE
            """
        ),
        {
            "name": "A-CN Gel",
            "composition": "Clindamycin (1% w/w) + Nicotinamide (4% w/w)",
            "manufacturer": "Eskon Pharma",
            "uses": "Điều trị mụn trứng cá theo chỉ định",
            "source_name": SOURCE_NAME,
            "source_ref": "https://www.apollopharmacy.in/medicine/a-cn-gel-20gm",
            "source_record_key": "eskon-a-cn-gel-20gm",
        },
    )


def downgrade() -> None:
    op.get_bind().execute(
        sa.text(
            "DELETE FROM medications "
            "WHERE source_name = :source_name AND source_record_key = :record_key"
        ),
        {"source_name": SOURCE_NAME, "record_key": "eskon-a-cn-gel-20gm"},
    )
