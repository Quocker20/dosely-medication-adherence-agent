from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from src.agents.nodes.scope_guard_node import ScopeClassification, scope_guard_node


@pytest.mark.asyncio
async def test_scope_blocks_when_classified_out_of_scope():
    verdict = ScopeClassification(category="out_of_scope", reason="thể thao", confidence=0.99)
    with patch(
        "src.agents.nodes.scope_guard_node.get_llm",
        **{"return_value.with_structured_output.return_value.ainvoke": AsyncMock(return_value=verdict)},
    ):
        result = await scope_guard_node({"messages": [HumanMessage(content="World Cup kết thúc khi nào?")]})
    assert result["scope_blocked"] is True
    assert result["scope_category"] == "out_of_scope"
    assert "ngoài phạm vi" in result["messages"][0].content


@pytest.mark.asyncio
async def test_scope_failure_defers_to_semantic_parser():
    with patch(
        "src.agents.nodes.scope_guard_node.get_llm",
        **{"return_value.with_structured_output.return_value.ainvoke": AsyncMock(side_effect=TimeoutError)},
    ):
        result = await scope_guard_node({"messages": [HumanMessage(content="câu diễn đạt lạ")]})
    assert result == {"scope_blocked": False, "scope_category": "unknown"}


@pytest.mark.asyncio
async def test_scope_classifier_receives_recent_context():
    verdict = ScopeClassification(category="medication", reason="follow-up", confidence=0.98)
    invoke = AsyncMock(return_value=verdict)
    with patch(
        "src.agents.nodes.scope_guard_node.get_llm",
        **{"return_value.with_structured_output.return_value.ainvoke": invoke},
    ):
        result = await scope_guard_node(
            {
                "messages": [
                    HumanMessage(content="Tôi hỏi về thuốc"),
                    AIMessage(content="Bạn muốn biết gì?"),
                    HumanMessage(content="Ý tôi là phần đó"),
                ]
            }
        )
    assert result["scope_blocked"] is False
    sent = invoke.await_args.args[0][1]["content"]
    assert "Bạn muốn biết gì" in sent and "Ý tôi là phần đó" in sent


@pytest.mark.asyncio
@pytest.mark.parametrize("message", ["Hôm nay tôi ngủ trễ", "Tối qua tôi thức khuya"])
async def test_routine_deviation_stays_in_scope(message: str):
    verdict = ScopeClassification(category="medication", reason="routine deviation", confidence=0.98)
    with patch(
        "src.agents.nodes.scope_guard_node.get_llm",
        **{"return_value.with_structured_output.return_value.ainvoke": AsyncMock(return_value=verdict)},
    ):
        result = await scope_guard_node({"messages": [HumanMessage(content=message)]})

    assert result == {"scope_blocked": False, "scope_category": "medication"}
