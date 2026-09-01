from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.messages import HumanMessage

from src.agents.nodes.plan_guard_node import plan_guard_node
from src.agents.nodes.semantic_planner_node import semantic_planner_node
from src.agents.semantic_plan import SemanticPlan, SemanticStep


@pytest.mark.asyncio
async def test_semantic_planner_selects_single_schedule_tool_with_filters():
    parsed = SemanticPlan(
        purpose="Tìm thuốc lúc 17h hôm nay",
        steps=[
            SemanticStep(
                id="step_1",
                tool="get_schedule",
                purpose="Tra lịch 17h hôm nay",
                date_reference="today",
                schedule_time="17:00",
                topics=["identity", "dose_status"],
                confidence=0.98,
            )
        ],
        confidence=0.98,
    )
    with patch(
        "src.agents.nodes.semantic_planner_node.get_llm",
        **{"return_value.with_structured_output.return_value.ainvoke": AsyncMock(return_value=parsed)},
    ):
        result = await semantic_planner_node(
            {"messages": [HumanMessage(content="5h chiều nay tôi có thuốc gì cần uống không?")]}
        )
    assert result["intent"] == "ask_schedule"
    assert result["intent_analysis"]["schedule_time"] == "17:00"
    assert result["use_legacy_classifier"] is False


@pytest.mark.asyncio
async def test_post_plan_guard_blocks_treatment_change_before_tool_execution():
    plan = SemanticPlan(
        purpose="Xin tự tăng liều",
        steps=[
            SemanticStep(
                id="step_1",
                tool="search_drug_knowledge",
                purpose="Xin tự tăng liều",
                drug_name="Paracetamol",
                requested_action="change_treatment",
            )
        ],
    )
    result = await plan_guard_node({"semantic_plan": plan.model_dump()})
    assert result["safety_blocked"] is True
    assert result["semantic_plan_valid"] is False
    assert "không thể tự quyết định" in result["messages"][0].content


@pytest.mark.asyncio
async def test_invalid_semantic_plan_falls_back_without_executing_tool():
    result = await plan_guard_node({"semantic_plan": {"tool": "read_entire_database"}})
    assert result["semantic_plan_valid"] is False
    assert result["use_legacy_classifier"] is True


@pytest.mark.asyncio
async def test_semantic_planner_marks_combined_plan_for_multi_tool_executor():
    parsed = SemanticPlan(
        purpose="Xem lịch và tra cứu thuốc",
        steps=[
            SemanticStep(id="step_1", tool="get_schedule", purpose="Xem lịch hôm nay"),
            SemanticStep(
                id="step_2",
                tool="search_drug_knowledge",
                purpose="Tra công dụng Paracetamol",
                drug_name="Paracetamol",
                topics=["indication"],
            ),
        ],
        confidence=0.94,
    )
    with patch(
        "src.agents.nodes.semantic_planner_node.get_llm",
        **{"return_value.with_structured_output.return_value.ainvoke": AsyncMock(return_value=parsed)},
    ):
        result = await semantic_planner_node(
            {"messages": [HumanMessage(content="Cho tôi lịch hôm nay và công dụng Paracetamol")]}
        )
    assert result["intent"] == "multi_tool"
    assert len(result["semantic_plan"]["steps"]) == 2


@pytest.mark.asyncio
async def test_post_plan_guard_rejects_two_write_steps():
    plan = SemanticPlan(
        purpose="Báo hai thay đổi",
        steps=[
            SemanticStep(
                id="step_1",
                tool="report_meal_shift",
                purpose="Báo đổi bữa sáng",
                requested_action="change_schedule",
            ),
            SemanticStep(
                id="step_2",
                tool="report_meal_shift",
                purpose="Báo đổi bữa tối",
                requested_action="change_schedule",
            ),
        ],
    )
    result = await plan_guard_node({"semantic_plan": plan.model_dump()})
    assert result["semantic_plan_valid"] is False
    assert result["safety_blocked"] is True
    assert "multiple_write_steps" in result["plan_errors"]


@pytest.mark.asyncio
async def test_post_plan_guard_accepts_adverse_event_with_symptom():
    plan = SemanticPlan(
        purpose="Ghi nhận buồn nôn",
        steps=[
            SemanticStep(
                id="step_1",
                tool="record_adverse_event",
                purpose="Ghi nhận triệu chứng",
                symptoms=[{"name": "buồn nôn", "severity": "MODERATE"}],
                requested_action="other",
            )
        ],
    )
    result = await plan_guard_node({"semantic_plan": plan.model_dump()})
    assert result["semantic_plan_valid"] is True
