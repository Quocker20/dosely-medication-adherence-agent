from unittest.mock import AsyncMock

import pytest
from langchain_core.messages import HumanMessage

from src.agents.nodes import prescribed_drug_info_node as node
from src.agents.prescribed_drug_resolver import ResolutionResult, ResolutionStatus


@pytest.mark.asyncio
async def test_multiple_matches_asks_clarification_and_never_calls_rag(monkeypatch):
    monkeypatch.setattr(node, "resolve_prescribed_drug", AsyncMock(return_value=ResolutionResult(
        ResolutionStatus.RESOLVED_MULTIPLE,
        [{"medication_name": "Drug A"}, {"medication_name": "Drug B"}],
        "dose_period",
    )))
    rag = AsyncMock()
    monkeypatch.setattr(node, "_lookup_exact_drug", rag)
    result = await node.prescribed_drug_info_node({"messages": [HumanMessage(content="Thuốc sáng có tác dụng gì?")]})
    assert "Drug A" in result["messages"][0].content
    assert "Drug B" in result["messages"][0].content
    rag.assert_not_called()


@pytest.mark.asyncio
async def test_missed_dose_answer_is_drug_scoped_and_never_instructs_double_dose(monkeypatch):
    monkeypatch.setattr(node, "resolve_prescribed_drug", AsyncMock(return_value=ResolutionResult(
        ResolutionStatus.RESOLVED_ONE,
        [{"medication_id": "m1", "medication_name": "Drug A", "status": "MISSED"}],
        "schedule_time", "07:00",
    )))
    monkeypatch.setattr(node, "_lookup_exact_drug", lambda *_: ("Thông tin đã đối chiếu đúng thuốc.", True))
    result = await node.prescribed_drug_info_node({
        "messages": [HumanMessage(content="Tôi quên thuốc 7 giờ, uống bù được không?")],
        "intent_analysis": {"topics": ["identity", "missed_dose"]},
    })
    answer = result["messages"][0].content
    assert "Drug A" in answer
    assert "không thể kết luận" in answer
    assert "Không uống gấp đôi" in answer
    assert result["metadata"]["resolved_medication"]["medication_id"] == "m1"
