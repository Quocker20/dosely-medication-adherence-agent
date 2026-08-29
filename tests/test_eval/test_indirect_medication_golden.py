import json
from pathlib import Path


CASES = json.loads(
    (Path(__file__).resolve().parents[2] / "eval" / "indirect_medication_golden_cases.json").read_text(encoding="utf-8")
)


def test_golden_set_is_broad_and_has_unique_ids():
    assert len(CASES) >= 18
    assert len({case["id"] for case in CASES}) == len(CASES)
    assert {case.get("reference_type") for case in CASES} >= {
        "schedule_time", "dose_period", "recent_dose", "next_dose",
        "meal_relation", "prescription_ordinal", "recent_context",
    }
    covered_topics = {topic for case in CASES for topic in case.get("topics", [])}
    assert covered_topics >= {
        "identity", "indication", "administration", "adverse_effect",
        "interaction", "contraindication", "missed_dose", "storage",
    }
    assert any(case.get("expected_scope_blocked") for case in CASES)
    assert any(case.get("expected_input_blocked") for case in CASES)
    assert any(case.get("expected_emergency") for case in CASES)
