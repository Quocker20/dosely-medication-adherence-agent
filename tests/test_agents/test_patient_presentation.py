from datetime import date
from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.messages import AIMessage

from src.agents.patient_presentation import patient_facing_text
from src.modules.agents.service import ChatService


def test_patient_facing_text_removes_internal_markers_but_keeps_layout():
    raw = (
        "Thuốc được hỏi\nParacetamol\n\n"
        "Tác dụng chính\n- Giảm đau [Nguồn 1].\n- Hạ sốt [Nguồn 2].\n\n"
        "Nguồn 1: Dược thư Quốc gia, trang 120"
    )
    result = patient_facing_text(raw)
    assert result == ("Thuốc được hỏi\nParacetamol\n\nTác dụng chính\n- Giảm đau.\n- Hạ sốt.")
    assert "Nguồn" not in result


def test_patient_facing_text_does_not_remove_normal_use_of_word_source():
    assert patient_facing_text("Thực phẩm là nguồn vitamin C.") == ("Thực phẩm là nguồn vitamin C.")


@pytest.mark.asyncio
async def test_chat_api_boundary_scrubs_citations_from_any_graph_branch():
    invoke = AsyncMock(
        return_value={
            "messages": [AIMessage(content="Paracetamol giúp hạ sốt [Nguồn 1].")],
            "intent": "general",
        }
    )
    with (
        patch(
            "src.modules.agents.service.get_patient_address",
            new=AsyncMock(return_value="bạn"),
        ),
        patch("src.modules.agents.service.agent.ainvoke", new=invoke),
    ):
        response, _ = await ChatService()._run_agent("Paracetamol có tác dụng gì?", "patient-123", date(2026, 8, 29))

    assert response == "Paracetamol giúp hạ sốt."
    assert "Nguồn" not in response
