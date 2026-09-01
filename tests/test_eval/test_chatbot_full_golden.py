import json
from pathlib import Path

from src.agents.medication_policy import match_medication_decision
from src.agents.semantic_plan import SemanticStep


CASES = json.loads(
    (Path(__file__).resolve().parents[2] / "eval" / "chatbot_full_golden_cases.json")
    .read_text(encoding="utf-8")
)


def test_full_golden_has_unique_ids_and_required_shape():
    assert len(CASES) >= 60
    assert len({case["id"] for case in CASES}) == len(CASES)
    for case in CASES:
        assert case.get("question") or case.get("turns")
        assert case.get("category")
        expected = case.get("expected")
        assert isinstance(expected, dict)
        assert expected.get("disposition") in {
            "allowed", "blocked", "escalated", "clarification",
            "blocked_or_clarification", "grounded_or_safe_refusal",
        }


def test_full_golden_covers_all_chatbot_capabilities():
    categories = {case["category"] for case in CASES}
    required = {
        "guardrail_prompt_injection", "guardrail_privacy",
        "guardrail_treatment_change", "emergency", "scope_blocked",
        "schedule_today", "next_dose", "current_medications",
        "explain_prescription", "drug_information", "drug_catalog_only",
        "indirect_drug_reference", "adverse_event_report", "meal_shift",
        "conversation_context",
    }
    assert required <= categories


def test_refusal_cases_have_at_most_one_expected_reason():
    for case in CASES:
        reason = case["expected"].get("reason")
        assert not isinstance(reason, list), case["id"]


def test_grounded_cases_are_drug_knowledge_cases():
    grounded = [case for case in CASES if case["expected"].get("grounding") is True]
    assert len(grounded) >= 7
    assert sum(
        case["expected"].get("disposition") == "grounded_or_safe_refusal"
        for case in CASES
    ) >= 2
    assert all(
        case["category"] in {
            "drug_information", "drug_brand_mapped", "hallucination_correction",
            "adverse_effect_question", "conversation_context",
        }
        for case in grounded
    )


def test_every_expected_intent_is_a_supported_chat_intent():
    supported = {
        "general", "clarify", "ask_schedule", "ask_next_dose",
        "ask_my_medications", "explain_my_medications", "ask_drug_info",
        "ask_prescribed_drug_info", "report_adverse_event", "report_meal_shift",
    }
    for case in CASES:
        assert set(case["expected"].get("intents") or []) <= supported, case["id"]


def test_adverse_event_report_is_not_a_take_medication_decision():
    assert match_medication_decision(
        "Sau khi uống thuốc tôi thực sự bị buồn nôn, ghi nhận giúp tôi."
    ) is None


def test_semantic_schema_supports_personal_medication_tools():
    current = SemanticStep(
        id="step_1", tool="get_current_medications", purpose="Xem thuốc hiện tại"
    )
    explain = SemanticStep(
        id="step_1", tool="explain_current_medications", purpose="Giải thích đơn"
    )
    assert current.tool == "get_current_medications"
    assert explain.tool == "explain_current_medications"
