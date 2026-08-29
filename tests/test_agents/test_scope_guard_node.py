from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.messages import HumanMessage

from src.agents.nodes.scope_guard_node import ScopeClassification, scope_guard_node


@pytest.mark.asyncio
async def test_world_cup_is_blocked_before_answer_generation():
    verdict = ScopeClassification(
        category="out_of_scope", reason="Câu hỏi thể thao", confidence=0.99
    )
    with patch(
        "src.agents.nodes.scope_guard_node.get_llm",
        **{"return_value.with_structured_output.return_value.ainvoke": AsyncMock(return_value=verdict)},
    ):
        result = await scope_guard_node({
            "messages": [HumanMessage(content="World Cup 2026 kết thúc ngày bao nhiêu?")]
        })
    assert result["scope_blocked"] is True
    assert result["scope_category"] == "out_of_scope"
    assert "ngoài phạm vi" in result["messages"][0].content


@pytest.mark.asyncio
async def test_scope_llm_failure_fails_closed_for_unknown_input():
    with patch(
        "src.agents.nodes.scope_guard_node.get_llm",
        **{"return_value.with_structured_output.return_value.ainvoke": AsyncMock(side_effect=TimeoutError)},
    ):
        result = await scope_guard_node({
            "messages": [HumanMessage(content="Viết cho tôi một bài thơ về bóng đá")]
        })
    assert result["scope_blocked"] is True


@pytest.mark.asyncio
@pytest.mark.parametrize("question", [
    "Lịch uống thuốc hôm nay",
    "Liều tiếp theo lúc mấy giờ?",
    "Tôi đau bụng sau khi uống thuốc",
    "Hôm nay ngày bao nhiêu",
    "Xin chào",
])
async def test_obvious_product_scope_does_not_need_llm(question):
    with patch("src.agents.nodes.scope_guard_node.get_llm") as get_llm:
        result = await scope_guard_node({"messages": [HumanMessage(content=question)]})
    assert result["scope_blocked"] is False
    get_llm.assert_not_called()
