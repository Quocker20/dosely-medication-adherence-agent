from unittest.mock import AsyncMock, patch
import pytest
from langchain_core.messages import HumanMessage
from src.agents.nodes.adverse_event_node import adverse_event_node


@pytest.mark.asyncio
async def test_adverse_event_node_records_structured_event_and_never_claims_causality():
    get_mock = AsyncMock(side_effect=[
        {"medications": [{"medication_id": "00000000-0000-0000-0000-000000000003", "display_name": "Paracetamol"}]},
        {"doses": []},
    ])
    with patch("src.agents.nodes.adverse_event_node.get", get_mock), patch(
        "src.agents.nodes.adverse_event_node.post", AsyncMock(return_value={"id": "event-1"})
    ) as post:
        result = await adverse_event_node({
            "patient_id": "00000000-0000-0000-0000-000000000001",
            "conversation_id": "00000000-0000-0000-0000-000000000002",
            "messages": [HumanMessage(content="Tôi hơi buồn nôn sau khi uống thuốc")],
            "intent_analysis": {"symptoms": [{"name": "buồn nôn", "severity": "MILD"}]},
        })
    payload = post.await_args.kwargs["json"]
    assert payload["risk_level"] == "LOW"
    assert payload["symptoms"][0]["name"] == "buồn nôn"
    assert payload["related_medications"][0]["drug_name"] == "Paracetamol"
    assert payload["related_medications"][0]["context_type"] == "ACTIVE_PRESCRIPTION"
    assert "chưa khẳng định thuốc là nguyên nhân" in result["messages"][0].content
