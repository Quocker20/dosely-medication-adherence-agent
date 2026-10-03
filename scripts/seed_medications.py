"""Seed the relational medication catalog (not the Chroma/RAG store)."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any

SOURCE_NAME = "WHO_EML_2023_STARTER"
SOURCE_REF = "https://www.who.int/publications/i/item/WHO-MHP-HPS-EML-2023.02"
DEFAULT_CATALOG = Path(__file__).resolve().parent / "data" / "who_eml_2023_starter.json"


def load_catalog(path: Path) -> list[dict[str, str]]:
    raw: Any = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list) or not raw:
        raise ValueError("Medication catalog must be a non-empty JSON array")
    rows: list[dict[str, str]] = []
    seen_keys: set[str] = set()
    seen_names: set[str] = set()
    for index, item in enumerate(raw, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"Catalog row {index} must be an object")
        row = {field: str(item.get(field, "")).strip() for field in ("key", "name", "composition")}
        if not all(row.values()):
            raise ValueError(f"Catalog row {index} requires key, name and composition")
        normalized_name = row["name"].casefold()
        if row["key"] in seen_keys or normalized_name in seen_names:
            raise ValueError(f"Duplicate medication at catalog row {index}: {row['name']}")
        seen_keys.add(row["key"])
        seen_names.add(normalized_name)
        rows.append(row)
    return rows


async def seed(rows: list[dict[str, str]]) -> int:
    from sqlalchemy.dialects.postgresql import insert
    from src.core.database import AsyncSessionLocal
    from src.modules.prescriptions.models import Medication

    values = [{
        "name": row["name"], "composition": row["composition"],
        "manufacturer": None, "uses": None, "side_effects": None, "image_url": None,
        "source_name": SOURCE_NAME, "source_ref": SOURCE_REF,
        "source_record_key": row["key"], "is_active": True,
    } for row in rows]
    statement = insert(Medication).values(values)
    statement = statement.on_conflict_do_update(
        index_elements=[Medication.source_name, Medication.source_record_key],
        index_where=Medication.source_record_key.is_not(None),
        set_={"name": statement.excluded.name, "composition": statement.excluded.composition,
              "source_ref": statement.excluded.source_ref, "is_active": True},
    )
    async with AsyncSessionLocal() as session:
        async with session.begin():
            await session.execute(statement)
    return len(values)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Upsert the Dosely medication catalog")
    parser.add_argument("--file", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--dry-run", action="store_true", help="Validate only; do not connect to PostgreSQL")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    rows = load_catalog(args.file)
    if args.dry_run:
        print(f"Validated {len(rows)} medications")
        return
    count = asyncio.run(seed(rows))
    print(f"Upserted {count} medications")


if __name__ == "__main__":
    main()
