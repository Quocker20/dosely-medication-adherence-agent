import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from src.agents.nodes.safety_guard_node import evaluate_safety, safety_guard_node


def _mock_llm(content: str):
    patcher = patch("src.agents.nodes.safety_guard_node.get_llm")
    mock_get_llm = patcher.start()
    mock_get_llm.return_value.ainvoke = AsyncMock(return_value=AIMessage(content=content))
    return patcher, mock_get_llm


@pytest.mark.asyncio
async def test_layer1_keyword_match_escalates_without_calling_llm():
    patcher, mock_get_llm = _mock_llm("KHONG")
    try:
        verdict = await evaluate_safety("tôi thấy tức ngực quá", "patient-1")
    finally:
        patcher.stop()

    assert verdict.escalated is True
    assert "tức ngực" in verdict.reason
    mock_get_llm.assert_not_called()


@pytest.mark.asyncio
async def test_layer1_match_with_llm_saying_not_severe_still_escalates():
    """Case kế hoạch yêu cầu: câu có keyword, LLM (nếu có bị gọi nhầm) nói
    'không nghiêm trọng' -> vẫn phải alert. Lớp 2 không được hủy Lớp 1."""
    patcher, _ = _mock_llm("KHONG nghiêm trọng đâu")
    try:
        verdict = await evaluate_safety("dạo này hay bị đau ngực lắm", "patient-1")
    finally:
        patcher.stop()

    assert verdict.escalated is True
    assert verdict.fixed_reply is not None


@pytest.mark.asyncio
async def test_layer2_llm_classifies_severe_when_no_keyword_matches():
    patcher, _ = _mock_llm("CO")
    try:
        verdict = await evaluate_safety("người tôi cứ lịm dần đi, không biết sao nữa", "patient-1")
    finally:
        patcher.stop()

    assert verdict.escalated is True
    assert verdict.reason == "SEVERE_SYMPTOM: llm_classified"


@pytest.mark.asyncio
async def test_layer2_llm_says_not_severe_no_escalation():
    patcher, _ = _mock_llm("KHONG")
    try:
        verdict = await evaluate_safety("hôm nay hơi mệt vì đi bộ nhiều", "patient-1")
    finally:
        patcher.stop()

    assert verdict.escalated is False


@pytest.mark.asyncio
async def test_layer2_timeout_fails_open_no_escalation_no_raise():
    patcher = patch("src.agents.nodes.safety_guard_node.get_llm")
    mock_get_llm = patcher.start()

    async def _hang(*_args, **_kwargs):
        await asyncio.sleep(10)

    mock_get_llm.return_value.ainvoke = _hang
    try:
        with patch("src.agents.nodes.safety_guard_node._LLM_TIMEOUT_SECONDS", 0.05):
            verdict = await evaluate_safety("bình thường thôi", "patient-1")
    finally:
        patcher.stop()

    assert verdict.escalated is False


@pytest.mark.asyncio
async def test_layer2_exception_fails_open_no_escalation_no_raise():
    patcher = patch("src.agents.nodes.safety_guard_node.get_llm")
    mock_get_llm = patcher.start()
    mock_get_llm.return_value.ainvoke = AsyncMock(side_effect=RuntimeError("boom"))
    try:
        verdict = await evaluate_safety("bình thường thôi", "patient-1")
    finally:
        patcher.stop()

    assert verdict.escalated is False


@pytest.mark.asyncio
async def test_graph_node_returns_fixed_reply_and_escalated_flag():
    patcher, _ = _mock_llm("KHONG")
    try:
        state = {
            "messages": [HumanMessage(content="tôi bị co giật")],
            "patient_id": "patient-1",
        }
        result = await safety_guard_node(state)
    finally:
        patcher.stop()

    assert result["escalated"] is True
    assert len(result["messages"]) == 1
    assert "115" in result["messages"][0].content


@pytest.mark.asyncio
async def test_graph_node_benign_message_does_not_add_reply():
    patcher, _ = _mock_llm("KHONG")
    try:
        state = {
            "messages": [HumanMessage(content="hôm nay tôi uống thuốc chưa nhỉ")],
            "patient_id": "patient-1",
        }
        result = await safety_guard_node(state)
    finally:
        patcher.stop()

    assert result["escalated"] is False
    assert "messages" not in result
