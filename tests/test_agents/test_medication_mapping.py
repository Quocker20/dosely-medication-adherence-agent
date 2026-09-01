from src.agents.medication_mapping import ingredient_candidates, resolve_catalog_medication
from src.rag_retrieval.service import DrugRAG


def test_composition_parser_removes_strength_without_losing_ingredients():
    assert ingredient_candidates("Doxycycline (100mg)") == ["Doxycycline"]
    assert ingredient_candidates("Amoxicillin 500mg; clavulanic acid 125mg") == [
        "Amoxicillin",
        "clavulanic acid",
    ]
    assert ingredient_candidates("Clindamycin (1% w/w) + Nicotinamide (4% w/w)") == ["Clindamycin", "Nicotinamide"]


def test_catalog_brand_resolves_via_composition_not_brand_fuzzy_match():
    rag = DrugRAG(client=object())
    resolved = resolve_catalog_medication("A Doxid 100mg Capsule", "Doxycycline (100mg)", rag)
    assert len(resolved) == 1
    assert resolved[0].formulary_name == "DOXYCYCLIN"


def test_combination_brand_resolves_every_active_ingredient():
    rag = DrugRAG(client=object())
    resolved = resolve_catalog_medication("A-CN Gel", "Clindamycin (1% w/w) + Nicotinamide (4% w/w)", rag)
    assert [(item.ingredient, item.formulary_name) for item in resolved] == [
        ("Clindamycin", "CLINDAMYCIN"),
        ("Nicotinamide", "NICOTINAMID"),
    ]


def test_lookalike_ingredient_is_not_automatically_mapped_to_another_drug():
    rag = DrugRAG(client=object())
    normalized, display = rag.infer_drug("Budesonide")
    assert display != "DESONID"
