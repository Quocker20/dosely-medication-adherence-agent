from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.messages import AIMessage

from src.chatbot.nodes.output_guard_node import output_guard_node, validate_patient_output


def test_output_guard_blocks_direct_medication_change_advice():
    assert "unsafe_treatment_directive" in validate_patient_output("Bạn nên ngừng thuốc ngay.")
    assert not validate_patient_output("Không tự ngừng thuốc hoặc đổi liều.")


def test_output_guard_blocks_english_patient_facing_labels_but_allows_drug_names():
    assert "english_patient_facing_label" in validate_patient_output("Status: PENDING")
    assert not validate_patient_output("07:00 - Paracetamol - Chưa uống")


@pytest.mark.asyncio
async def test_output_guard_replaces_unsafe_answer():
    result = await output_guard_node({"messages": [AIMessage(content="Bạn có thể uống bù liều.")]})
    assert result["output_guarded"] is False
    assert "an toàn" in result["messages"][0].content


@pytest.mark.asyncio
async def test_output_guard_allows_deterministic_schedule_answer():
    result = await output_guard_node({"messages": [AIMessage(content="Cữ tiếp theo là A lúc 19:00.")]})
    assert result["output_guarded"] is True


_RG = "src.chatbot.nodes.output_guard_node.generate_refusal"
_NOTICE = "Dosely đã gửi cảnh báo tới bác sĩ của bạn."


def _escalated_state(**extra):
    return {
        "messages": [AIMessage(content="Hãy bấm giữ nút Alert. Nếu nguy hiểm tức thời, hãy gọi cấp cứu 115 ngay.")],
        "escalated": True,
        "refusal_reason": "SEVERE_SYMPTOM: co giật",
        **extra,
    }


@pytest.mark.asyncio
async def test_escalated_refusal_failure_keeps_emergency_instructions_and_notice():
    with patch(_RG, AsyncMock(side_effect=RuntimeError("llm down"))):
        result = await output_guard_node(_escalated_state(red_alert_notified=True))
    text = result["messages"][0].content
    assert "115" in text and "Alert" in text
    assert text.rstrip().endswith(_NOTICE)


@pytest.mark.asyncio
async def test_escalated_refusal_without_115_gets_emergency_sentence():
    with patch(_RG, AsyncMock(return_value="Bạn hãy bình tĩnh nhé.")):
        result = await output_guard_node(_escalated_state(red_alert_notified=True))
    text = result["messages"][0].content
    assert "115" in text
    assert text.rstrip().endswith(_NOTICE)


@pytest.mark.asyncio
async def test_non_escalated_refusal_does_not_get_115_sentence():
    state = {"messages": [AIMessage(content="Bạn có thể uống bù liều.")]}
    with patch(_RG, AsyncMock(return_value="Mình không thể tư vấn việc này.")):
        result = await output_guard_node(state)
    assert "115" not in result["messages"][0].content
