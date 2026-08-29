from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.messages import HumanMessage

from src.agents.nodes import scheduled_drug_info_node as module
from src.agents.nodes.classify_intent_node import IntentClassification, classify_intent_node


@pytest.mark.asyncio
async def test_empty_stomach_question_uses_time_to_resolve_drug_not_list_schedule():
    semantic_result = IntentClassification(
        intent="ask_schedule",
        topics=["administration", "adverse_effect"],
        reference_type="schedule_time",
        schedule_time="07:30",
        symptoms=["đau bụng"],
        requested_action="check_instructions",
        confidence=0.94,
    )
    with patch(
        "src.agents.nodes.classify_intent_node.get_llm",
        **{"return_value.with_structured_output.return_value.ainvoke": AsyncMock(return_value=semantic_result)},
    ):
        result = await classify_intent_node({"messages": [HumanMessage(content=(
            "Tôi bị đau bụng, chắc do uống thuốc lúc đói, tra hộ tôi xem dùng thuốc ở cữ 7h30 như thế có sai không?"
        ))]})
    assert result["intent"] == "ask_prescribed_drug_info"
    assert result["intent_analysis"]["schedule_time"] == "07:30"
    assert result["intent_analysis"]["symptoms"] == ["đau bụng"]


@pytest.mark.asyncio
async def test_effect_question_about_timed_dose_uses_special_route():
    semantic_result = IntentClassification(
        intent="ask_scheduled_drug_info",
        topics=["indication"],
        reference_type="schedule_time",
        schedule_time="07:30",
        requested_action="explain",
        confidence=0.98,
    )
    with patch(
        "src.agents.nodes.classify_intent_node.get_llm",
        **{"return_value.with_structured_output.return_value.ainvoke": AsyncMock(return_value=semantic_result)},
    ):
        result = await classify_intent_node({
            "messages": [HumanMessage(content="Thuốc ở cữ 07:30 có tác dụng gì?")]
        })
    assert result["intent"] == "ask_prescribed_drug_info"


@pytest.mark.asyncio
async def test_semantic_parser_failure_keeps_safe_deterministic_fallback():
    with patch(
        "src.agents.nodes.classify_intent_node.get_llm",
        **{"return_value.with_structured_output.return_value.ainvoke": AsyncMock(side_effect=TimeoutError)},
    ):
        result = await classify_intent_node({"messages": [HumanMessage(content=(
            "Thuốc ở cữ 7h30 uống lúc đói có sai không?"
        ))]})
    assert result["intent"] == "ask_prescribed_drug_info"
    assert result["intent_analysis"]["parser"] == "deterministic"


@pytest.mark.asyncio
async def test_node_resolves_only_authenticated_patients_exact_timed_drug(monkeypatch):
    backend_get = AsyncMock(return_value={
        "date": "2026-08-29",
        "timezone": "Asia/Ho_Chi_Minh",
        "doses": [{
            "current_scheduled_at": "2026-08-29T00:30:00Z",
            "medication_name": "A Doxid 100mg Capsule",
            "meal_relation": "AFTER_MEAL",
        }],
    })
    monkeypatch.setattr(module, "get", backend_get)
    monkeypatch.setattr(module, "_lookup_exact_drug", lambda name, question: (
        "Thuốc có chỉ định và phản ứng bất lợi đã được tra cứu.", True
    ))

    result = await module.scheduled_drug_info_node({
        "patient_id": "patient-from-jwt",
        "client_date": "2026-08-29",
        "messages": [HumanMessage(content="Thuốc cữ 7h30 có tác dụng gì?")],
    })

    backend_get.assert_awaited_once_with(
        "/patients/patient-from-jwt/schedules", params={"date": "2026-08-29"}
    )
    answer = result["messages"][0].content
    assert "A Doxid 100mg Capsule" in answer
    assert "sau bữa ăn" in answer
    assert "Abel 40" not in answer


@pytest.mark.asyncio
async def test_multiple_drugs_at_same_time_requires_clarification(monkeypatch):
    monkeypatch.setattr(module, "get", AsyncMock(return_value={
        "date": "2026-08-29",
        "timezone": "Asia/Ho_Chi_Minh",
        "doses": [
            {"current_scheduled_at": "2026-08-29T00:30:00Z", "medication_name": "Drug A"},
            {"current_scheduled_at": "2026-08-29T00:30:00Z", "medication_name": "Drug B"},
        ],
    }))
    result = await module.scheduled_drug_info_node({
        "patient_id": "patient-from-jwt",
        "client_date": "2026-08-29",
        "messages": [HumanMessage(content="Thuốc cữ 7h30 có tác dụng gì?")],
    })
    answer = result["messages"][0].content
    assert "Drug A" in answer and "Drug B" in answer
    assert "thuốc nào" in answer
