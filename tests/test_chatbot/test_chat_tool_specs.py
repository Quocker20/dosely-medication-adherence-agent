"""TDD specs for lane C (chat prompt, rescheduling errors, graph, reviewer, adherence stats, output guard)."""

from __future__ import annotations

from datetime import date, timedelta
from typing import get_args
from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from src.chatbot.graph import _route_after_plan_guard, build_graph
from src.chatbot.nodes.output_guard_node import validate_patient_output
from src.chatbot.nodes.plan_guard_node import validate_plan
from src.chatbot.nodes.rescheduling_node import RoutineDeviationExtraction, rescheduling_node
from src.chatbot.nodes.semantic_output_reviewer_node import Review, semantic_output_reviewer_node
from src.chatbot.semantic_plan import TOOL_TO_LEGACY_INTENT, SemanticPlan, SemanticStep, SemanticTool

LEAK = "secret-db-host:5432"


# ---------------------------------------------------------------- C-01
def test_chat_prompt_does_not_mention_uncallable_tools():  # spec: C-01
    from src.chatbot.nodes.chat_node import SYSTEM_PROMPT

    assert "search_drug_info" not in SYSTEM_PROMPT
    assert "search_drug_formulary" not in SYSTEM_PROMPT
    assert "gọi tool" not in SYSTEM_PROMPT


def test_chat_prompt_keeps_safety_and_language_rules():  # spec: C-01
    from src.chatbot.nodes.chat_node import SYSTEM_PROMPT

    assert "KHÔNG tự kê đơn, đổi liều" in SYSTEM_PROMPT
    assert "bằng tiếng Việt" in SYSTEM_PROMPT


# ---------------------------------------------------------------- C-02
@pytest.mark.asyncio
async def test_rescheduling_node_never_leaks_exception_text():  # spec: C-02
    extraction = RoutineDeviationExtraction(event="routine_deviation", anchor="lunch", new_time="14:00")
    with (
        patch(
            "src.chatbot.nodes.rescheduling_node.get_llm",
            **{"return_value.with_structured_output.return_value.ainvoke": AsyncMock(return_value=extraction)},
        ),
        patch("src.chatbot.nodes.rescheduling_node.get_recent_routine_overrides") as history,
        patch("src.chatbot.nodes.rescheduling_node.report_routine_deviation") as tool,
    ):
        history.ainvoke = AsyncMock(return_value="[]")
        tool.ainvoke = AsyncMock(side_effect=Exception(LEAK))
        result = await rescheduling_node(
            {"messages": [HumanMessage(content="hôm nay tôi ăn trưa muộn, 2 giờ chiều")], "patient_id": "p1"}
        )
    assert result["messages"]
    assert all(LEAK not in str(m.content) for m in result["messages"])


# ---------------------------------------------------------------- C-03
def test_classify_intent_not_in_compiled_graph():  # spec: C-03
    assert "classify_intent" not in build_graph().get_graph().nodes


# ---------------------------------------------------------------- C-04
def _reviewer_state(intent: str) -> dict:
    return {
        "messages": [HumanMessage(content="hỏi"), AIMessage(content="Câu trả lời từ dữ liệu.")],
        "intent": intent,
        "grounding_valid": True,
    }


@pytest.mark.parametrize(
    "intent",
    [
        "ask_schedule",
        "ask_next_dose",
        "ask_my_medications",
        "get_recent_adverse_event",
        "clarify",
        "report_meal_shift",
        "report_adverse_event",
    ],
)
@pytest.mark.asyncio
async def test_reviewer_skips_llm_for_deterministic_intents(intent):  # spec: C-04
    with patch("src.chatbot.nodes.semantic_output_reviewer_node.get_llm") as llm:
        result = await semantic_output_reviewer_node(_reviewer_state(intent))
    llm.assert_not_called()
    assert "messages" not in result  # answer unchanged


@pytest.mark.parametrize("intent", ["agent", "general", "explain_my_medications"])
@pytest.mark.asyncio
async def test_reviewer_still_calls_llm_for_free_text_intents(intent):  # spec: C-04
    review = Review(decision="approve", reason="ok")
    with patch(
        "src.chatbot.nodes.semantic_output_reviewer_node.get_llm",
        **{"return_value.with_structured_output.return_value.ainvoke": AsyncMock(return_value=review)},
    ) as llm:
        await semantic_output_reviewer_node(_reviewer_state(intent))
    llm.assert_called()


# ---------------------------------------------------------------- C-05
def test_adherence_tool_is_a_semantic_tool_mapped_to_legacy_intent():  # spec: C-05
    assert "get_adherence_stats" in get_args(SemanticTool)
    assert TOOL_TO_LEGACY_INTENT.get("get_adherence_stats") == "ask_adherence_stats"


def test_adherence_plan_is_valid_and_routes_to_adherence_stats_node():  # spec: C-05
    plan = SemanticPlan(
        purpose="t",
        steps=[SemanticStep(id="step_1", tool="get_adherence_stats", purpose="t", confidence=0.99)],
        confidence=0.99,
    )
    assert validate_plan(plan) == []
    assert _route_after_plan_guard({"intent": "ask_adherence_stats", "semantic_plan_valid": True}) == "adherence_stats"
    assert "adherence_stats" in build_graph().get_graph().nodes


@pytest.mark.asyncio
async def test_adherence_stats_node_reads_last_seven_days_and_replies_in_vietnamese():  # spec: C-05
    from src.chatbot.nodes import adherence_stats_node as module

    summary = {
        "patient_id": "p1",
        "from_date": "2026-11-02",
        "to_date": "2026-11-08",
        "adherence_rate": 0.8,
        "total_doses": 10,
        "taken_doses": 8,
        "skipped_doses": 1,
        "missed_doses": 1,
    }
    get = AsyncMock(return_value=summary)
    post = AsyncMock()
    with patch.object(module, "get", get):
        if hasattr(module, "post"):
            module.post = post
        result = await module.adherence_stats_node(
            {
                "patient_id": "p1",
                "client_date": "2026-11-08",
                "messages": [HumanMessage(content="tuần này tôi uống đủ chưa")],
            }
        )
    get.assert_awaited_once()
    assert get.await_args.args[0] == "/patients/p1/adherence"
    params = get.await_args.kwargs["params"]
    end = date.fromisoformat("2026-11-08")
    assert params["to"] == end.isoformat()
    assert date.fromisoformat(params["to"]) - date.fromisoformat(params["from"]) in {
        timedelta(days=6),
        timedelta(days=7),
    }
    answer = result["messages"][0].content
    assert "8" in answer and "10" in answer
    assert "80" in answer
    post.assert_not_awaited()


@pytest.mark.asyncio
async def test_adherence_stats_node_backend_error_is_generic_vietnamese():  # spec: C-05
    from src.chatbot.nodes import adherence_stats_node as module

    with patch.object(module, "get", AsyncMock(side_effect=Exception(LEAK))):
        result = await module.adherence_stats_node(
            {
                "patient_id": "p1",
                "client_date": "2026-11-08",
                "messages": [HumanMessage(content="tuần này tôi uống đủ chưa")],
            }
        )
    answer = result["messages"][0].content
    assert LEAK not in answer
    assert answer.strip()


# ---------------------------------------------------------------- C-06
@pytest.mark.parametrize(
    "text",
    [
        "Bạn có thể ngừng thuốc nếu thấy khỏe.",
        "Bạn nên tự tăng liều lên 2 viên.",
        "Bạn cứ uống gấp đôi nhé.",
        "Bạn không cần uống nữa.",
        "Bạn có thể tạm ngưng thuốc vài ngày.",
    ],
)
def test_dangerous_directive_variants_are_flagged(text):  # spec: C-06
    assert "unsafe_treatment_directive" in validate_patient_output(text)


@pytest.mark.parametrize(
    "text",
    [
        "Bạn không nên tự ngừng thuốc.",
        "Đừng tự tăng liều nhé.",
        "Hãy hỏi bác sĩ trước khi đổi liều.",
        "Bác sĩ dặn không được bỏ thuốc.",
    ],
)
def test_safe_phrasings_are_not_flagged(text):  # spec: C-06
    assert "unsafe_treatment_directive" not in validate_patient_output(text)
