from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from src.agents.graph import agent


@pytest.mark.asyncio
async def test_agent_answers_directly_without_tool_calls():
    """LLM trả lời ngay, không cần gọi tool -> graph kết thúc sau 1 vòng."""
    reply = AIMessage(content="Xin chào, tôi có thể giúp gì cho bạn?")

    with patch("src.agents.nodes.chat_node.get_llm") as mock_get_llm:
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

    with patch("src.agents.nodes.chat_node.get_llm") as mock_get_llm:
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
