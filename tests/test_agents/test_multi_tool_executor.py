from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from src.agents.nodes.multi_tool_executor_node import multi_tool_executor_node
from src.agents.semantic_plan import SemanticPlan, SemanticStep


@pytest.mark.asyncio
async def test_multi_tool_executor_runs_steps_in_order_and_combines_answers():
    schedule = AsyncMock(return_value={"messages": [AIMessage(content="07:00 - Thuốc A - Đã uống")]})
    lookup = AsyncMock(return_value={
        "messages": [AIMessage(content="Paracetamol giúp giảm đau, hạ sốt.")],
        "metadata": {"sources": 1},
    })
    plan = SemanticPlan(
        purpose="Xem lịch và công dụng thuốc",
        steps=[
            SemanticStep(id="step_1", tool="get_schedule", purpose="Lịch hôm nay"),
            SemanticStep(
                id="step_2", tool="search_drug_information",
                purpose="Công dụng Paracetamol", drug_name="Paracetamol",
                topics=["indication"],
            ),
        ],
    )
    with patch.dict(
        "src.agents.nodes.multi_tool_executor_node._EXECUTORS",
        {"get_schedule": schedule, "search_drug_information": lookup},
    ):
        result = await multi_tool_executor_node({
            "messages": [HumanMessage(content="Lịch hôm nay và công dụng Paracetamol")],
            "semantic_plan": plan.model_dump(),
        })

    schedule.assert_awaited_once()
    lookup.assert_awaited_once()
    assert "07:00 - Thuốc A - Đã uống" in result["messages"][0].content
    assert "Paracetamol giúp giảm đau" in result["messages"][0].content
    assert "Lịch hôm nay" not in result["messages"][0].content
    assert "Kết quả 1" in result["messages"][0].content
    assert result["metadata"]["semantic_steps"]["step_2"] == {"sources": 1}
