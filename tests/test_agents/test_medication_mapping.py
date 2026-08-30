from src.agents.medication_mapping import ingredient_candidates, resolve_catalog_medication
from src.rag_retrieval.service import DrugRAG


def test_composition_parser_removes_strength_without_losing_ingredients():
    assert ingredient_candidates("Doxycycline (100mg)") == ["Doxycycline"]
    assert ingredient_candidates("Amoxicillin 500mg; clavulanic acid 125mg") == [
        "Amoxicillin", "clavulanic acid",
    ]


def test_catalog_brand_resolves_via_composition_not_brand_fuzzy_match():
    rag = DrugRAG(client=object())
    resolved = resolve_catalog_medication(
        "A Doxid 100mg Capsule", "Doxycycline (100mg)", rag
    )
    assert len(resolved) == 1
    assert resolved[0].formulary_name == "DOXYCYCLIN"


def test_lookalike_ingredient_is_not_automatically_mapped_to_another_drug():
    rag = DrugRAG(client=object())
    normalized, display = rag.infer_drug("Budesonide")
    assert display != "DESONID"

