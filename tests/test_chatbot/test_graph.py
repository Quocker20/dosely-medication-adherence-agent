from contextlib import ExitStack
from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from src.chatbot.graph import _route_after_plan_guard, _route_after_semantic_planner, agent
from src.chatbot.nodes.rescheduling_node import RoutineDeviationExtraction
from src.chatbot.nodes.scope_guard_node import ScopeClassification
from src.chatbot.semantic_plan import TOOL_TO_LEGACY_INTENT, SemanticPlan, SemanticStep


def _not_severe():
    """safety_guard_node giờ chạy trước mọi thứ (graph.py) — mock lớp 2 của
    nó trả 'KHONG' để các test không đụng LLM thật, và message test không
    chứa từ khóa Lớp 1 nên không escalate."""
    return patch(
        "src.chatbot.nodes.safety_guard_node.get_llm",
        **{"return_value.ainvoke": AsyncMock(return_value=AIMessage(content="KHONG"))},
    )


def _in_scope():
    return patch(
        "src.chatbot.nodes.scope_guard_node.get_llm",
        **{
            "return_value.with_structured_output.return_value.ainvoke": AsyncMock(
                return_value=ScopeClassification(category="medication", reason="test", confidence=1.0)
            )
        },
    )


def _planned_as(intent: str):
    """semantic_planner chạy sau scope_guard (classify_intent không còn nằm trên
    đường chính) — mock nó trả sẵn 1 plan 1 bước ánh xạ về `intent`."""
    tool = next(t for t, i in TOOL_TO_LEGACY_INTENT.items() if i == intent)
    plan = SemanticPlan(
        purpose="test",
        steps=[
            SemanticStep(
                id="step_1",
                tool=tool,
                purpose="test",
                drug_name="Acid ascorbic" if intent == "ask_drug_info" else None,
                confidence=0.99,
            )
        ],
        confidence=0.99,
    )
    return patch(
        "src.chatbot.nodes.semantic_planner_node.get_llm",
        **{"return_value.with_structured_output.return_value.ainvoke": AsyncMock(return_value=plan)},
    )


def _refusal_llm(reply: str | None = "Câu trả lời từ chối đã được tạo."):
    """output_guard sinh câu từ chối qua refusal_response.get_llm (không còn là
    văn bản cố định) — mock để test không đụng LLM thật; reply=None -> LLM lỗi
    nên output_guard dùng _SAFE_FALLBACK."""
    if reply is None:
        return patch("src.chatbot.nodes.refusal_response.get_llm", side_effect=RuntimeError("refusal llm down"))
    return patch(
        "src.chatbot.nodes.refusal_response.get_llm",
        **{"return_value.ainvoke": AsyncMock(return_value=AIMessage(content=reply))},
    )


def _reaches_agent(intent: str = "general"):
    """safety_guard, scope_guard và semantic_planner đều pass-through, luồng tới
    node đích của `intent`."""
    stack = ExitStack()
    stack.enter_context(_not_severe())
    stack.enter_context(_in_scope())
    stack.enter_context(_planned_as(intent))
    return stack


@pytest.mark.asyncio
async def test_agent_answers_directly_without_tool_calls():
    """LLM trả lời ngay, không cần gọi tool -> graph kết thúc sau 1 vòng."""
    reply = AIMessage(content="Xin chào, tôi có thể giúp gì cho bạn?")

    with _reaches_agent(), patch("src.chatbot.nodes.chat_node.get_llm") as mock_get_llm:
        mock_get_llm.return_value.ainvoke = AsyncMock(return_value=reply)

        result = await agent.ainvoke({"messages": [HumanMessage(content="Xin chào")], "patient_id": "patient-123"})

    assert result["messages"][-1].content == "Xin chào, tôi có thể giúp gì cho bạn?"


@pytest.mark.asyncio
async def test_generic_agent_has_no_tools_under_least_privilege():
    reply = AIMessage(content="Mình có thể hỗ trợ trong phạm vi Dosely.")
    with _reaches_agent(intent="general"), patch("src.chatbot.nodes.chat_node.get_llm") as mock_get_llm:
        mock_get_llm.return_value.ainvoke = AsyncMock(return_value=reply)
        result = await agent.ainvoke({"messages": [HumanMessage(content="Xin chào")], "patient_id": "patient-123"})
    mock_get_llm.return_value.bind_tools.assert_not_called()
    assert result["messages"][-1].content == reply.content


@pytest.mark.asyncio
async def test_agent_calls_formulary_rag_only_after_safety_passes():
    from src.rag_retrieval.safe_service import SafeRAGResult

    rag_result = SafeRAGResult(
        answer="Acid ascorbic điều trị thiếu vitamin C [Nguồn 1].",
        status="answered",
        safety_reason=None,
        grounding_valid=True,
        grounding_errors=[],
        sources=[],
    )
    with (
        _reaches_agent(intent="ask_drug_info"),
        patch("src.chatbot.nodes.chat_node.get_llm") as mock_get_llm,
        patch("src.chatbot.nodes.drug_rag_node._get_rag_service") as mock_rag,
    ):
        mock_rag.return_value.rag.infer_drug.return_value = ("acid ascorbic", "Acid ascorbic")
        mock_rag.return_value.query.return_value = rag_result
        result = await agent.ainvoke(
            {
                "messages": [HumanMessage(content="Acid ascorbic có chỉ định gì?")],
                "patient_id": "patient-123",
            }
        )

    mock_get_llm.assert_not_called()
    mock_rag.return_value.query.assert_called_once_with(
        "Acid ascorbic có chỉ định gì?", context_drug=("acid ascorbic", "Acid ascorbic")
    )
    answer = result["messages"][-1].content
    assert "Tác dụng hoặc chỉ định chính" in answer
    assert "- Acid ascorbic điều trị thiếu vitamin C." in answer
    assert "Khi cần xác nhận thêm" in answer
    assert "[Nguồn" not in answer
    assert result["grounding_valid"] is True


@pytest.mark.asyncio
async def test_graph_replaces_uncited_formulary_answer_with_safe_fallback():
    from src.rag_retrieval.safe_service import SafeRAGResult

    rag_result = SafeRAGResult(
        answer="Mình chưa thể xác minh câu trả lời hoàn toàn từ các đoạn Dược thư đã truy xuất. Bạn vui lòng hỏi bác sĩ hoặc dược sĩ.",
        status="grounding_blocked",
        safety_reason=None,
        grounding_valid=False,
        grounding_errors=["missing_citation"],
        sources=[],
    )

    with (
        _reaches_agent(intent="ask_drug_info"),
        _refusal_llm(None),  # LLM từ chối lỗi -> output_guard dùng _SAFE_FALLBACK
        patch("src.chatbot.nodes.drug_rag_node._get_rag_service") as mock_rag,
    ):
        mock_rag.return_value.rag.infer_drug.return_value = ("acid ascorbic", "Acid ascorbic")
        mock_rag.return_value.query.return_value = rag_result
        result = await agent.ainvoke(
            {
                "messages": [HumanMessage(content="Acid ascorbic có chỉ định gì?")],
                "patient_id": "patient-123",
            }
        )

    assert result["grounding_valid"] is False
    assert "missing_citation" in result["grounding_errors"]
    assert "cung cấp câu trả lời này một cách an toàn" in result["messages"][-1].content


@pytest.mark.asyncio
async def test_severe_symptom_short_circuits_before_planner_and_chat():
    """safety_guard escalate -> graph dừng ngay, semantic_planner VÀ
    agent_node (LLM trò chuyện) đều không bao giờ được gọi."""
    with (
        patch("src.chatbot.nodes.semantic_planner_node.get_llm") as mock_classify_llm,
        patch("src.chatbot.nodes.chat_node.get_llm") as mock_chat_llm,
        _refusal_llm("Hãy gọi 115 ngay."),
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
    # Câu trả lời cuối do refusal LLM sinh từ lý do SEVERE_SYMPTOM (không còn cố định).
    assert result["refusal_reason"].startswith("SEVERE_SYMPTOM")
    assert result["messages"][-1].content == "Hãy gọi 115 ngay."


@pytest.mark.asyncio
async def test_medication_decision_short_circuits_before_planner_chat_and_rag():
    with (
        patch("src.chatbot.nodes.semantic_planner_node.get_llm") as mock_classify_llm,
        patch("src.chatbot.nodes.chat_node.get_llm") as mock_chat_llm,
        patch("src.chatbot.nodes.drug_rag_node._get_rag_service") as mock_rag,
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
async def test_drug_recommendation_is_blocked_before_planner_chat_and_rag():
    with (
        patch("src.chatbot.nodes.semantic_planner_node.get_llm") as mock_classify_llm,
        patch("src.chatbot.nodes.chat_node.get_llm") as mock_chat_llm,
        patch("src.chatbot.nodes.drug_rag_node._get_rag_service") as mock_rag,
        _refusal_llm("Mình không thể gợi ý thuốc."),
    ):
        result = await agent.ainvoke(
            {
                "messages": [HumanMessage(content="Tôi không thích ăn rau, có thuốc nào hỗ trợ giấc ngủ không?")],
                "patient_id": "patient-123",
            }
        )

    mock_classify_llm.assert_not_called()
    mock_chat_llm.assert_not_called()
    mock_rag.assert_not_called()
    assert result["safety_blocked"] is True
    assert result["refusal_reason"]
    assert result["messages"][-1].content == "Mình không thể gợi ý thuốc."


@pytest.mark.asyncio
async def test_out_of_scope_question_stops_before_planner_and_chat_llm():
    with (
        _not_severe(),
        patch(
            "src.chatbot.nodes.scope_guard_node.get_llm",
            **{
                "return_value.with_structured_output.return_value.ainvoke": AsyncMock(
                    return_value=ScopeClassification(category="out_of_scope", reason="thể thao", confidence=1.0)
                )
            },
        ),
        patch("src.chatbot.nodes.semantic_planner_node.get_llm") as classifier_llm,
        patch("src.chatbot.nodes.chat_node.get_llm") as chat_llm,
        _refusal_llm("Câu hỏi này ngoài phạm vi hỗ trợ."),
    ):
        result = await agent.ainvoke(
            {
                "messages": [HumanMessage(content="World Cup 2026 kết thúc ngày bao nhiêu?")],
                "patient_id": "patient-123",
            }
        )
    classifier_llm.assert_not_called()
    chat_llm.assert_not_called()
    assert result["scope_blocked"] is True
    assert result["refusal_reason"] == "outside_dosely_scope"
    assert result["messages"][-1].content == "Câu hỏi này ngoài phạm vi hỗ trợ."


@pytest.mark.asyncio
async def test_meal_shift_intent_routes_to_rescheduling_not_chat_llm():
    """Semantic plan routes a routine deviation straight to rescheduling."""
    semantic_plan = SemanticPlan(
        purpose="Báo giờ ăn trưa hôm nay thay đổi",
        steps=[
            SemanticStep(
                id="step_1",
                tool="report_meal_shift",
                purpose="Dời mốc bữa trưa hôm nay",
                requested_action="change_schedule",
                confidence=0.99,
            )
        ],
        confidence=0.99,
    )
    with (
        _not_severe(),
        _in_scope(),
        patch(
            "src.chatbot.nodes.semantic_planner_node.get_llm",
            **{"return_value.with_structured_output.return_value.ainvoke": AsyncMock(return_value=semantic_plan)},
        ),
        patch(
            "src.chatbot.nodes.rescheduling_node.get_llm",
            **{
                "return_value.with_structured_output.return_value.ainvoke": AsyncMock(
                    return_value=RoutineDeviationExtraction(event="routine_deviation", anchor="lunch", new_time="14:00")
                )
            },
        ),
        patch("src.chatbot.nodes.rescheduling_node.report_routine_deviation") as mock_tool,
        patch("src.chatbot.nodes.chat_node.get_llm") as mock_chat_llm,
    ):
        mock_tool.ainvoke = AsyncMock(return_value="Đã rải lại lịch.")

        result = await agent.ainvoke(
            {
                "messages": [HumanMessage(content="hôm nay tôi ăn trưa muộn, 2 giờ chiều")],
                "patient_id": "patient-123",
                "client_date": "2026-08-14",
            }
        )

        mock_chat_llm.assert_not_called()

    assert result["intent"] == "report_meal_shift"
    assert "14:00" in result["messages"][-1].content


@pytest.mark.asyncio
async def test_should_continue_routes_on_tool_calls():
    from src.chatbot.nodes.chat_node import should_continue

    with_tool_calls = {"messages": [AIMessage(content="", tool_calls=[{"name": "x", "args": {}, "id": "1"}])]}
    without_tool_calls = {"messages": [AIMessage(content="done")]}

    assert should_continue(with_tool_calls) == "tools"
    assert should_continue(without_tool_calls) == "end"


def test_rag_node_is_only_reachable_after_safety_guard():
    """The deterministic RAG branch remains behind the graph safety gate."""
    from src.chatbot.graph import build_graph

    graph = build_graph().get_graph()
    start_targets = {edge.target for edge in graph.edges if edge.source == "__start__"}
    assert start_targets == {"safety_guard"}
    plan_guard_targets = {edge.target for edge in graph.edges if edge.source == "plan_guard"}
    assert "drug_rag" in plan_guard_targets
    # drug_rag chỉ có thể tới từ plan_guard (và classify_intent cũ, không còn nối vào entry).
    rag_sources = {edge.source for edge in graph.edges if edge.target == "drug_rag"}
    assert "safety_guard" not in rag_sources and "scope_guard" not in rag_sources
    safety_targets = {edge.target for edge in graph.edges if edge.source == "safety_guard"}
    assert "scope_guard" in safety_targets


def test_semantic_parser_degradation_routes_to_clarification():
    """classify_intent đã bị thay bằng semantic_planner; planner/plan lỗi -> hỏi lại, không đoán."""
    assert _route_after_semantic_planner({"use_legacy_classifier": True}) == "clarification"
    assert _route_after_plan_guard({"use_legacy_classifier": True, "semantic_plan_valid": False}) == "clarification"


def test_chat_system_prompt_guides_profile_based_addressing():
    from src.chatbot.nodes.chat_node import _build_system_message

    content = _build_system_message("patient-123", "chị").content

    assert 'Không mặc định mở đầu bằng "chào bác"' in content
    assert "Xưng hô đã được backend xác định từ hồ sơ: chị" in content
    assert "không cần gọi tool hồ sơ" in content
    assert "không tự suy đoán tuổi" in content
