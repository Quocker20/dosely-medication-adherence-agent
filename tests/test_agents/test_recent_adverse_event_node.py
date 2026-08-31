from unittest.mock import AsyncMock, patch
import pytest
from src.agents.nodes.recent_adverse_event_node import recent_adverse_event_node


@pytest.mark.asyncio
async def test_recent_adverse_event_reads_database_by_memory_pointer():
    with patch("src.agents.nodes.recent_adverse_event_node.get", AsyncMock(return_value={
        "symptoms": [{"name": "buồn nôn"}], "risk_level": "LOW",
    })) as get:
        result = await recent_adverse_event_node({
            "patient_id": "00000000-0000-0000-0000-000000000001",
            "memory_context": {"last_adverse_event_id": "00000000-0000-0000-0000-000000000002"},
        })
    get.assert_awaited_once()
    assert "buồn nôn" in result["messages"][0].content


@pytest.mark.asyncio
async def test_recent_adverse_event_does_not_guess_without_pointer():
    result = await recent_adverse_event_node({"memory_context": {}})
    assert "chưa có ghi nhận" in result["messages"][0].content
