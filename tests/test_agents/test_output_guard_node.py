import pytest
from langchain_core.messages import AIMessage

from src.agents.nodes.output_guard_node import output_guard_node, validate_patient_output


def test_output_guard_blocks_direct_medication_change_advice():
    assert "unsafe_treatment_directive" in validate_patient_output("Bạn nên ngừng thuốc ngay.")
    assert not validate_patient_output("Không tự ngừng thuốc hoặc đổi liều.")


@pytest.mark.asyncio
async def test_output_guard_replaces_unsafe_answer():
    result = await output_guard_node({"messages": [AIMessage(content="Bạn có thể uống bù liều.")]})
    assert result["output_guarded"] is False
    assert "an toàn" in result["messages"][0].content


@pytest.mark.asyncio
async def test_output_guard_allows_deterministic_schedule_answer():
    result = await output_guard_node({"messages": [AIMessage(content="Cữ tiếp theo là A lúc 19:00.")]})
    assert result["output_guarded"] is True
