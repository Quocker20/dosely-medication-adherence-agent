from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.messages import HumanMessage

from src.agents.nodes import drug_rag_node as module
from src.agents.nodes.classify_intent_node import IntentClassification, classify_intent_node


class FakeRag:
    def __init__(self, result):
        self.result = result

    def query(self, _question, **_kwargs):
        return self.result


def _semantic_parser(result: IntentClassification):
    parser = AsyncMock()
    parser.ainvoke.return_value = result
    llm = SimpleNamespace(with_structured_output=lambda _schema: parser)
    return llm


def _result(answer: str):
    return SimpleNamespace(
        answer=answer,
        status="answered",
        grounding_valid=True,
        grounding_errors=[],
        sources=[
            SimpleNamespace(drug_name="Paracetamol", citation="Dược thư", section="indications", excerpt="Paracetamol")
        ],
    )


@pytest.mark.asyncio
async def test_effect_answer_has_stable_patient_friendly_structure(monkeypatch):
    monkeypatch.setattr(
        module,
        "_get_rag_service",
        lambda: FakeRag(
            _result("- Paracetamol có tác dụng giảm đau [Nguồn 1].\n- Paracetamol có tác dụng hạ sốt [Nguồn 2].")
        ),
    )
    result = await module.drug_rag_node({"messages": [HumanMessage(content="Paracetamol có tác dụng gì?")]})
    answer = result["messages"][0].content
    assert "Thuốc được hỏi\nParacetamol" in answer
    assert "Tác dụng hoặc chỉ định chính" in answer
    assert "- Paracetamol có tác dụng giảm đau." in answer
    assert "Phạm vi của thông tin" in answer
    assert "Khi cần xác nhận thêm" in answer
    assert "[Nguồn" not in answer


@pytest.mark.asyncio
async def test_adverse_effect_question_is_not_mislabeled_as_main_effect(monkeypatch):
    monkeypatch.setattr(
        module, "_get_rag_service", lambda: FakeRag(_result("- Paracetamol có thể gây phản ứng bất lợi [Nguồn 1]."))
    )
    result = await module.drug_rag_node({"messages": [HumanMessage(content="Paracetamol có tác dụng phụ gì?")]})
    answer = result["messages"][0].content
    assert "Tác dụng hoặc chỉ định chính" not in answer
    assert "Tác dụng phụ hoặc phản ứng bất lợi" in answer
    assert "Paracetamol có thể gây phản ứng bất lợi." in answer


def test_effect_formatter_keeps_each_claim_with_its_drug_section():
    answer = module._format_effect_answer(
        "- Chỉ định thứ nhất [Nguồn 1].\n- Chỉ định thứ hai [Nguồn 1].",
        "Metformin",
    )
    assert answer.index("Metformin") < answer.index("Chỉ định thứ nhất")
    assert answer.index("Chỉ định thứ nhất") < answer.index("Chỉ định thứ hai")


@pytest.mark.parametrize(
    ("question", "heading"),
    [
        ("Amoxicillin chống chỉ định khi nào?", "Trường hợp không được dùng theo Dược Thư"),
        ("Warfarin có tương tác gì?", "Tương tác được ghi nhận"),
        ("Metformin bảo quản thế nào?", "Hướng dẫn bảo quản"),
        ("Thuốc này dùng cho phụ nữ mang thai không?", "Thông tin cho nhóm đối tượng được hỏi"),
        ("Nếu quên liều metformin thì sao?", "Thông tin chung khi quên liều"),
        ("Cách dùng amoxicillin thế nào?", "Cách dùng chung trong Dược Thư"),
    ],
)
def test_drug_topics_have_distinct_headings(question: str, heading: str):
    assert module._drug_topic(question)[1] == heading


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "question",
    [
        "Paracetamol có tác dụng gì?",
        "Amoxicillin chống chỉ định khi nào?",
        "Warfarin có tương tác gì?",
        "Metformin bảo quản thế nào?",
    ],
)
async def test_clear_drug_questions_route_deterministically(question: str):
    with patch("src.agents.nodes.classify_intent_node.get_llm") as get_llm:
        result = await classify_intent_node({"messages": [HumanMessage(content=question)]})
    assert result["intent"] == "ask_drug_info"
    assert result["intent_analysis"]["reference_type"] == "drug_name"
    get_llm.assert_not_called()


@pytest.mark.asyncio
async def test_named_drug_how_to_use_routes_through_semantic_parser():
    analysis = IntentClassification(
        intent="ask_drug_info",
        topics=["administration"],
        reference_type="drug_name",
        drug_name="Paracetamol",
        confidence=0.98,
    )
    with patch("src.agents.nodes.classify_intent_node.get_llm", return_value=_semantic_parser(analysis)) as get_llm:
        result = await classify_intent_node({"messages": [HumanMessage(content="Paracetamol dùng như thế nào?")]})
    assert result["intent"] == "ask_drug_info"
    get_llm.assert_called_once()


@pytest.mark.asyncio
async def test_missed_morning_dose_question_routes_from_semantic_parser():
    analysis = IntentClassification(
        intent="ask_schedule",
        topics=["dose_status"],
        reference_type="dose_period",
        dose_period="morning",
        date_reference="today",
        requested_action="view_schedule",
        confidence=0.98,
    )
    with patch("src.agents.nodes.classify_intent_node.get_llm", return_value=_semantic_parser(analysis)) as get_llm:
        result = await classify_intent_node(
            {"messages": [HumanMessage(content="sáng hôm nay tôi có bỏ qua thuốc nào ko?")]}
        )
    assert result["intent"] == "ask_schedule"
    assert result["intent_analysis"]["topics"] == ["dose_status"]
    assert result["intent_analysis"]["dose_period"] == "morning"
    get_llm.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("question", "topic"),
    [
        ("A Doxid 100mg Capsule uống lúc nào?", "administration"),
        ("Tôi dùng Paracetamol nhưng bị dị ứng thì phải làm sao?", "adverse_effect"),
    ],
)
async def test_explicit_drug_questions_do_not_route_to_schedule_reference(question, topic):
    analysis = IntentClassification(
        intent="ask_drug_info",
        topics=[topic],
        reference_type="drug_name",
        drug_name="A Doxid 100mg Capsule",
        confidence=0.98,
    )
    with patch("src.agents.nodes.classify_intent_node.get_llm", return_value=_semantic_parser(analysis)) as get_llm:
        result = await classify_intent_node({"messages": [HumanMessage(content=question)]})
    assert result["intent"] == "ask_drug_info"
    assert result["intent_analysis"]["reference_type"] == "drug_name"
    assert topic in result["intent_analysis"]["topics"]
    get_llm.assert_called_once()


@pytest.mark.asyncio
async def test_bare_drug_name_asks_which_information_is_wanted():
    result = await module.drug_rag_node(
        {
            "messages": [HumanMessage(content="A Doxid 100mg Capsule")],
            "intent_analysis": {"drug_name": "A Doxid 100mg Capsule", "needs_clarification": True},
        }
    )
    answer = result["messages"][0].content
    assert "công dụng" in answer
    assert "cách dùng" in answer
    assert "tác dụng phụ" in answer
