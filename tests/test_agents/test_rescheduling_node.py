from unittest.mock import AsyncMock, patch

import pytest

from src.agents.nodes.rescheduling_node import MealShiftExtraction, handle_reschedule_request


def _mock_extraction(extraction: MealShiftExtraction):
    patcher = patch("src.agents.nodes.rescheduling_node.get_llm")
    mock_get_llm = patcher.start()
    mock_get_llm.return_value.with_structured_output.return_value.ainvoke = AsyncMock(
        return_value=extraction
    )
    return patcher


@pytest.mark.asyncio
async def test_clear_meal_shift_calls_reschedule_tool():
    extraction = MealShiftExtraction(event="meal_shift", meal="lunch", new_time="14:00")
    patcher = _mock_extraction(extraction)
    try:
        with patch(
            "src.agents.nodes.rescheduling_node.reschedule_remaining_doses"
        ) as mock_tool:
            mock_tool.ainvoke = AsyncMock(return_value="Đã rải lại lịch thành công.")
            result = await handle_reschedule_request(
                "hôm nay tôi ăn trưa muộn, tầm 2 giờ chiều", "patient-1"
            )
    finally:
        patcher.stop()

    assert result.status == "rescheduled"
    assert "14:00" in result.message
    mock_tool.ainvoke.assert_called_once()
    call_kwargs = mock_tool.ainvoke.call_args[0][0]
    assert call_kwargs["patient_id"] == "patient-1"
    assert "14:00" in call_kwargs["reason"]


@pytest.mark.asyncio
async def test_ambiguous_time_asks_clarifying_question_without_guessing():
    extraction = MealShiftExtraction(
        event="unclear",
        meal="lunch",
        clarifying_question="Bạn ăn trưa muộn khoảng mấy giờ vậy?",
    )
    patcher = _mock_extraction(extraction)
    try:
        with patch(
            "src.agents.nodes.rescheduling_node.reschedule_remaining_doses"
        ) as mock_tool:
            mock_tool.ainvoke = AsyncMock()
            result = await handle_reschedule_request("hôm nay tôi ăn trưa muộn", "patient-1")
    finally:
        patcher.stop()

    assert result.status == "needs_clarification"
    assert result.message == "Bạn ăn trưa muộn khoảng mấy giờ vậy?"
    mock_tool.ainvoke.assert_not_called()


@pytest.mark.asyncio
async def test_meal_shift_without_new_time_is_treated_as_unclear():
    """Phòng trường hợp LLM gắn nhầm event=meal_shift nhưng lại quên
    new_time -- vẫn phải hỏi lại, không được gọi tool với giờ rỗng."""
    extraction = MealShiftExtraction(event="meal_shift", meal="lunch", new_time=None)
    patcher = _mock_extraction(extraction)
    try:
        with patch(
            "src.agents.nodes.rescheduling_node.reschedule_remaining_doses"
        ) as mock_tool:
            mock_tool.ainvoke = AsyncMock()
            result = await handle_reschedule_request("ăn trưa hơi trễ", "patient-1")
    finally:
        patcher.stop()

    assert result.status == "needs_clarification"
    mock_tool.ainvoke.assert_not_called()


@pytest.mark.asyncio
async def test_out_of_scope_request_is_refused_not_rescheduled():
    extraction = MealShiftExtraction(event="out_of_scope")
    patcher = _mock_extraction(extraction)
    try:
        with patch(
            "src.agents.nodes.rescheduling_node.reschedule_remaining_doses"
        ) as mock_tool:
            mock_tool.ainvoke = AsyncMock()
            result = await handle_reschedule_request("bỏ cữ tối luôn được không", "patient-1")
    finally:
        patcher.stop()

    assert result.status == "refused"
    assert "bác sĩ" in result.message.lower()
    mock_tool.ainvoke.assert_not_called()


@pytest.mark.asyncio
async def test_dose_change_request_is_refused():
    extraction = MealShiftExtraction(event="out_of_scope")
    patcher = _mock_extraction(extraction)
    try:
        with patch(
            "src.agents.nodes.rescheduling_node.reschedule_remaining_doses"
        ) as mock_tool:
            mock_tool.ainvoke = AsyncMock()
            result = await handle_reschedule_request("tăng liều lên 2 viên nhé", "patient-1")
    finally:
        patcher.stop()

    assert result.status == "refused"
    mock_tool.ainvoke.assert_not_called()


@pytest.mark.asyncio
async def test_llm_extraction_failure_asks_to_repeat_and_never_reschedules():
    patcher = patch("src.agents.nodes.rescheduling_node.get_llm")
    mock_get_llm = patcher.start()
    mock_get_llm.return_value.with_structured_output.return_value.ainvoke = AsyncMock(
        side_effect=RuntimeError("boom")
    )
    try:
        with patch(
            "src.agents.nodes.rescheduling_node.reschedule_remaining_doses"
        ) as mock_tool:
            mock_tool.ainvoke = AsyncMock()
            result = await handle_reschedule_request("hôm nay tôi ăn trưa muộn", "patient-1")
    finally:
        patcher.stop()

    assert result.status == "needs_clarification"
    mock_tool.ainvoke.assert_not_called()
