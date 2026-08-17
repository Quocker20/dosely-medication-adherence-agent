from contextlib import ExitStack
from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from src.agents.graph import agent
from src.agents.nodes.classify_intent_node import IntentClassification
from src.agents.nodes.rescheduling_node import MealShiftExtraction


def _not_severe():
    """safety_guard_node giờ chạy trước mọi thứ (graph.py) — mock lớp 2 của
    nó trả 'KHONG' để các test không đụng LLM thật, và message test không
    chứa từ khóa Lớp 1 nên không escalate."""
    return patch(
        "src.agents.nodes.safety_guard_node.get_llm",
        **{"return_value.ainvoke": AsyncMock(return_value=AIMessage(content="KHONG"))},
    )


def _classified_as(intent: str):
    """classify_intent_node chạy sau safety_guard, trước agent_node — mock
    nó trả sẵn 1 nhãn để test không phụ thuộc LLM thật phân loại đúng."""
    return patch(
        "src.agents.nodes.classify_intent_node.get_llm",
        **{
            "return_value.with_structured_output.return_value.ainvoke": AsyncMock(
                return_value=IntentClassification(intent=intent)
            )
        },
    )


def _reaches_agent(intent: str = "general"):
    """Cả safety_guard lẫn classify_intent đều pass-through, luồng tới agent_node."""
    stack = ExitStack()
    stack.enter_context(_not_severe())
    stack.enter_context(_classified_as(intent))
    return stack


@pytest.mark.asyncio
async def test_agent_answers_directly_without_tool_calls():
    """LLM trả lời ngay, không cần gọi tool -> graph kết thúc sau 1 vòng."""
    reply = AIMessage(content="Xin chào, tôi có thể giúp gì cho bạn?")

    with _reaches_agent(), patch("src.agents.nodes.chat_node.get_llm") as mock_get_llm:
        mock_get_llm.return_value.bind_tools.return_value.ainvoke = AsyncMock(return_value=reply)

        result = await agent.ainvoke(
            {"messages": [HumanMessage(content="Xin chào")], "patient_id": "patient-123"}
        )

    assert result["messages"][-1].content == "Xin chào, tôi có thể giúp gì cho bạn?"


@pytest.mark.asyncio
async def test_agent_calls_tool_then_answers():
    """LLM gọi search_drug_info trước, rồi dùng kết quả tool để trả lời."""
    tool_call_reply = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "search_drug_info",
                "args": {"query": "paracetamol"},
                "id": "call_1",
            }
        ],
    )
    final_reply = AIMessage(content="Đây là thông tin về paracetamol.")

    with (
        _reaches_agent(intent="ask_drug_info"),
        patch("src.agents.nodes.chat_node.get_llm") as mock_get_llm,
    ):
        mock_get_llm.return_value.bind_tools.return_value.ainvoke = AsyncMock(
            side_effect=[tool_call_reply, final_reply]
        )

        result = await agent.ainvoke(
            {
                "messages": [HumanMessage(content="Paracetamol dùng để làm gì?")],
                "patient_id": "patient-123",
            }
        )

    messages = result["messages"]
    tool_messages = [m for m in messages if m.__class__.__name__ == "ToolMessage"]
    assert len(tool_messages) == 1
    assert tool_messages[0].tool_call_id == "call_1"
    assert messages[-1].content == "Đây là thông tin về paracetamol."


@pytest.mark.asyncio
async def test_agent_calls_formulary_rag_only_after_safety_passes():
    tool_call_reply = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "search_drug_formulary",
                "args": {"query": "Acid ascorbic có chỉ định gì?"},
                "id": "rag_call_1",
            }
        ],
    )
    final_reply = AIMessage(content="Acid ascorbic được dùng theo [Nguồn 1].")
    grounded_context = (
        "[Nguồn 1] ACID ASCORBIC — Chỉ định, trang 100\n"
        "<du_lieu_duoc_thu>Điều trị thiếu vitamin C.</du_lieu_duoc_thu>"
    )

    with (
        _reaches_agent(intent="ask_drug_info"),
        patch("src.agents.nodes.chat_node.get_llm") as mock_get_llm,
        patch("src.agents.tools.drug_rag_tools._retrieve", return_value=grounded_context),
    ):
        mock_get_llm.return_value.bind_tools.return_value.ainvoke = AsyncMock(
            side_effect=[tool_call_reply, final_reply]
        )
        result = await agent.ainvoke(
            {
                "messages": [HumanMessage(content="Acid ascorbic có chỉ định gì?")],
                "patient_id": "patient-123",
            }
        )

    tool_messages = [
        message for message in result["messages"] if message.__class__.__name__ == "ToolMessage"
    ]
    assert len(tool_messages) == 1
    assert tool_messages[0].tool_call_id == "rag_call_1"
    assert "[Nguồn 1]" in tool_messages[0].content
    assert result["messages"][-1].content == final_reply.content


@pytest.mark.asyncio
async def test_graph_replaces_uncited_formulary_answer_with_safe_fallback():
    tool_call_reply = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "search_drug_formulary",
                "args": {"query": "Acid ascorbic có chỉ định gì?"},
                "id": "rag_call_bad",
            }
        ],
    )
    uncited_reply = AIMessage(content="Acid ascorbic chữa khỏi tất cả bệnh.")
    grounded_context = (
        "[Nguồn 1] ACID ASCORBIC — Chỉ định, trang 100\n"
        "<du_lieu_duoc_thu>Điều trị thiếu vitamin C.</du_lieu_duoc_thu>"
    )

    with (
        _reaches_agent(intent="ask_drug_info"),
        patch("src.agents.nodes.chat_node.get_llm") as mock_get_llm,
        patch("src.agents.tools.drug_rag_tools._retrieve", return_value=grounded_context),
    ):
        mock_get_llm.return_value.bind_tools.return_value.ainvoke = AsyncMock(
            side_effect=[tool_call_reply, uncited_reply]
        )
        result = await agent.ainvoke(
            {
                "messages": [HumanMessage(content="Acid ascorbic có chỉ định gì?")],
                "patient_id": "patient-123",
            }
        )

    assert result["grounding_valid"] is False
    assert "missing_citation" in result["grounding_errors"]
    assert "chưa thể xác minh" in result["messages"][-1].content


@pytest.mark.asyncio
async def test_severe_symptom_short_circuits_before_classify_and_chat():
    """safety_guard escalate -> graph dừng ngay, classify_intent VÀ
    agent_node (LLM trò chuyện) đều không bao giờ được gọi."""
    with (
        patch("src.agents.nodes.classify_intent_node.get_llm") as mock_classify_llm,
        patch("src.agents.nodes.chat_node.get_llm") as mock_chat_llm,
    ):
        result = await agent.ainvoke(
            {
                "messages": [HumanMessage(content="tôi thấy tức ngực với khó thở quá")],
                "patient_id": "patient-123",
            }
        )

        mock_classify_llm.assert_not_called()
        mock_chat_llm.assert_not_called()

    assert result["escalated"] is True
    assert "115" in result["messages"][-1].content


@pytest.mark.asyncio
async def test_medication_decision_short_circuits_before_classify_chat_and_rag():
    with (
        patch("src.agents.nodes.classify_intent_node.get_llm") as mock_classify_llm,
        patch("src.agents.nodes.chat_node.get_llm") as mock_chat_llm,
        patch("src.agents.tools.drug_rag_tools._retrieve") as mock_rag,
    ):
        result = await agent.ainvoke(
            {
                "messages": [HumanMessage(content="Tôi tăng gấp đôi liều được không?")],
                "patient_id": "patient-123",
            }
        )
    mock_classify_llm.assert_not_called()
    mock_chat_llm.assert_not_called()
    mock_rag.assert_not_called()
    assert result["safety_blocked"] is True
    assert result["escalated"] is False


@pytest.mark.asyncio
async def test_meal_shift_intent_routes_to_rescheduling_not_chat_llm():
    """classify_intent -> report_meal_shift -> rescheduling_node, agent_node
    (chat LLM tự do) không bao giờ được gọi."""
    with (
        _not_severe(),
        _classified_as("report_meal_shift"),
        patch(
            "src.agents.nodes.rescheduling_node.get_llm",
            **{
                "return_value.with_structured_output.return_value.ainvoke": AsyncMock(
                    return_value=MealShiftExtraction(event="meal_shift", meal="lunch", new_time="14:00")
                )
            },
        ),
        patch("src.agents.nodes.rescheduling_node.reschedule_remaining_doses") as mock_tool,
        patch("src.agents.nodes.chat_node.get_llm") as mock_chat_llm,
    ):
        mock_tool.ainvoke = AsyncMock(return_value="Đã rải lại lịch.")

        result = await agent.ainvoke(
            {
                "messages": [HumanMessage(content="hôm nay tôi ăn trưa muộn, 2 giờ chiều")],
                "patient_id": "patient-123",
            }
        )

        mock_chat_llm.assert_not_called()

    assert result["intent"] == "report_meal_shift"
    assert "14:00" in result["messages"][-1].content


@pytest.mark.asyncio
async def test_should_continue_routes_on_tool_calls():
    from src.agents.nodes.chat_node import should_continue

    with_tool_calls = {
        "messages": [
            AIMessage(content="", tool_calls=[{"name": "x", "args": {}, "id": "1"}])
        ]
    }
    without_tool_calls = {"messages": [AIMessage(content="done")]}

    assert should_continue(with_tool_calls) == "tools"
    assert should_continue(without_tool_calls) == "end"


def test_rag_tool_is_only_reachable_after_safety_guard():
    """RAG belongs to CHAT_TOOLS; graph entry remains the deterministic guard."""
    from src.agents.graph import build_graph
    from src.agents.tools import CHAT_TOOLS

    assert "search_drug_formulary" in {tool.name for tool in CHAT_TOOLS}
    graph = build_graph().get_graph()
    start_targets = {edge.target for edge in graph.edges if edge.source == "__start__"}
    assert start_targets == {"safety_guard"}
