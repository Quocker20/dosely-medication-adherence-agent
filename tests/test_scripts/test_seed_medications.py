import json

import pytest

from scripts.seed_medications import DEFAULT_CATALOG, load_catalog


def test_starter_medication_catalog_is_valid_and_substantial():
    rows = load_catalog(DEFAULT_CATALOG)
    assert len(rows) >= 60
    assert len({row["key"] for row in rows}) == len(rows)
    assert len({row["name"].casefold() for row in rows}) == len(rows)
    assert {"Paracetamol", "Amlodipine", "Metformin"}.issubset({row["name"] for row in rows})


def test_catalog_rejects_duplicate_keys(tmp_path):
    catalog = tmp_path / "duplicate.json"
    catalog.write_text(json.dumps([
        {"key": "same", "name": "Medicine A", "composition": "A"},
        {"key": "same", "name": "Medicine B", "composition": "B"},
    ]), encoding="utf-8")
    with pytest.raises(ValueError, match="Duplicate medication"):
        load_catalog(catalog)
