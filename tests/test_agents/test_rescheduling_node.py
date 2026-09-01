from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from src.agents.nodes.rescheduling_node import (
    RoutineDeviationExtraction,
    handle_reschedule_request,
)


def _mock_extraction(extraction: RoutineDeviationExtraction):
    patcher = patch("src.agents.nodes.rescheduling_node.get_llm")
    mock_get_llm = patcher.start()
    mock_get_llm.return_value.with_structured_output.return_value.ainvoke = AsyncMock(return_value=extraction)
    # Direct (non-structured) call path used only by _draft_history_aware_question.
    mock_get_llm.return_value.ainvoke = AsyncMock(return_value=SimpleNamespace(content=""))
    return patcher


def _mock_no_history():
    """Cold-start default: no prior RoutineOverride for this anchor."""
    patcher = patch("src.agents.nodes.rescheduling_node.get_recent_routine_overrides")
    mock_tool = patcher.start()
    mock_tool.ainvoke = AsyncMock(return_value="[]")
    return patcher


@pytest.mark.asyncio
async def test_clear_routine_deviation_calls_report_tool():
    extraction = RoutineDeviationExtraction(event="routine_deviation", anchor="lunch", new_time="14:00")
    patcher = _mock_extraction(extraction)
    history_patcher = _mock_no_history()
    try:
        with patch("src.agents.nodes.rescheduling_node.report_routine_deviation") as mock_tool:
            mock_tool.ainvoke = AsyncMock(return_value="Đã rải lại lịch thành công.")
            result = await handle_reschedule_request("hôm nay tôi ăn trưa muộn, tầm 2 giờ chiều", "patient-1")
    finally:
        patcher.stop()
        history_patcher.stop()

    assert result.status == "rescheduled"
    assert "14:00" in result.message
    mock_tool.ainvoke.assert_called_once()
    call_kwargs = mock_tool.ainvoke.call_args[0][0]
    assert call_kwargs["patient_id"] == "patient-1"
    assert call_kwargs["anchor"] == "lunch"
    assert call_kwargs["overridden_time"] == "14:00"
    # An offset, never a date the node computed itself.
    assert call_kwargs["day_offset"] == 0
    assert "override_date" not in call_kwargs
    assert "14:00" in call_kwargs["reason"]


@pytest.mark.asyncio
async def test_sleep_shift_extraction_routes_to_report_tool_with_sleep_anchor():
    extraction = RoutineDeviationExtraction(event="routine_deviation", anchor="sleep", new_time="01:00")
    patcher = _mock_extraction(extraction)
    history_patcher = _mock_no_history()
    try:
        with patch("src.agents.nodes.rescheduling_node.report_routine_deviation") as mock_tool:
            mock_tool.ainvoke = AsyncMock(return_value="Đã rải lại lịch thành công.")
            result = await handle_reschedule_request("hôm nay tôi ngủ trễ, khoảng 1 giờ sáng", "patient-1")
    finally:
        patcher.stop()
        history_patcher.stop()

    assert result.status == "rescheduled"
    mock_tool.ainvoke.assert_called_once()
    call_kwargs = mock_tool.ainvoke.call_args[0][0]
    assert call_kwargs["anchor"] == "sleep"
    assert call_kwargs["overridden_time"] == "01:00"


@pytest.mark.asyncio
async def test_ambiguous_time_asks_clarifying_question_without_guessing():
    extraction = RoutineDeviationExtraction(
        event="unclear",
        anchor="lunch",
        clarifying_question="Bạn ăn trưa muộn khoảng mấy giờ vậy?",
    )
    patcher = _mock_extraction(extraction)
    history_patcher = _mock_no_history()
    try:
        with patch("src.agents.nodes.rescheduling_node.report_routine_deviation") as mock_tool:
            mock_tool.ainvoke = AsyncMock()
            result = await handle_reschedule_request("hôm nay tôi ăn trưa muộn", "patient-1")
    finally:
        patcher.stop()
        history_patcher.stop()

    assert result.status == "needs_clarification"
    assert result.message == "Bạn ăn trưa muộn khoảng mấy giờ vậy?"
    mock_tool.ainvoke.assert_not_called()


@pytest.mark.asyncio
async def test_unclear_with_history_gets_a_smarter_question_but_still_asks():
    """Có lịch sử báo lệch giờ gần đây cho đúng anchor -> câu hỏi được làm
    giàu bằng LLM, nhưng vẫn phải là needs_clarification — tuyệt đối không
    được tự nhảy sang rescheduled chỉ vì có lịch sử."""
    extraction = RoutineDeviationExtraction(
        event="unclear",
        anchor="dinner",
        clarifying_question="Bạn ăn tối muộn khoảng mấy giờ vậy?",
    )
    patcher = _mock_extraction(extraction)
    suggested_question = "Bạn ăn tối lúc khoảng 20:00 như mấy hôm trước phải không, hay hôm nay giờ khác?"
    with patch("src.agents.nodes.rescheduling_node.get_llm") as mock_get_llm:
        mock_get_llm.return_value.with_structured_output.return_value.ainvoke = AsyncMock(return_value=extraction)
        mock_get_llm.return_value.ainvoke = AsyncMock(return_value=SimpleNamespace(content=suggested_question))
        with patch("src.agents.nodes.rescheduling_node.get_recent_routine_overrides") as mock_history_tool:
            mock_history_tool.ainvoke = AsyncMock(
                return_value='[{"override_date": "2026-08-10", "overridden_time": "20:00:00"}]'
            )
            with patch("src.agents.nodes.rescheduling_node.report_routine_deviation") as mock_write_tool:
                mock_write_tool.ainvoke = AsyncMock()
                result = await handle_reschedule_request("hôm nay tôi ăn tối muộn", "patient-1")

    try:
        assert result.status == "needs_clarification"
        assert result.message == suggested_question
        mock_write_tool.ainvoke.assert_not_called()
    finally:
        patcher.stop()


@pytest.mark.asyncio
async def test_backend_refusal_is_not_reported_as_a_successful_reschedule():
    """Nhánh nguy hiểm nhất: ý định hợp lệ nhưng backend từ chối ghi. Nếu
    vẫn trả "đã rải lại lịch", bệnh nhân tin là giờ đã đổi trong khi thực tế
    không có gì được ghi — và sẽ uống sai giờ."""
    extraction = RoutineDeviationExtraction(event="routine_deviation", anchor="lunch", new_time="14:00")
    patcher = _mock_extraction(extraction)
    history_patcher = _mock_no_history()
    try:
        with patch("src.agents.nodes.rescheduling_node.report_routine_deviation") as mock_tool:
            mock_tool.ainvoke = AsyncMock(
                return_value="Không báo được lệch giờ: Routine overrides can only apply to today's schedule"
            )
            result = await handle_reschedule_request("hôm nay tôi ăn trưa muộn, tầm 2 giờ chiều", "patient-1")
    finally:
        patcher.stop()
        history_patcher.stop()

    assert result.status == "failed"
    assert "Mình đã báo hệ thống" not in result.message


@pytest.mark.asyncio
async def test_relative_day_is_sent_as_an_offset_not_a_computed_date():
    """ "Ngày kia" phải đi ra ngoài dưới dạng offset=2. Node không được tự quy
    ra ngày — chỉ backend biết timezone của bệnh nhân."""
    extraction = RoutineDeviationExtraction(
        event="routine_deviation", anchor="dinner", new_time="21:00", target_day="day_after_tomorrow"
    )
    patcher = _mock_extraction(extraction)
    history_patcher = _mock_no_history()
    try:
        with patch("src.agents.nodes.rescheduling_node.report_routine_deviation") as mock_tool:
            mock_tool.ainvoke = AsyncMock(return_value="Đã rải lại lịch thành công.")
            result = await handle_reschedule_request("ngày kia tôi ăn tối lúc 9 giờ", "patient-1")
    finally:
        patcher.stop()
        history_patcher.stop()

    assert result.status == "rescheduled"
    assert mock_tool.ainvoke.call_args[0][0]["day_offset"] == 2
    assert "ngày kia" in result.message


@pytest.mark.asyncio
async def test_an_unrecognised_date_expression_is_asked_back_not_guessed():
    """LLM được dặn trả unclear cho "thứ 5"/"cuối tuần". Test này chốt hậu quả:
    không có tool ghi nào chạy khi ngày chưa chắc chắn."""
    extraction = RoutineDeviationExtraction(
        event="unclear",
        anchor="dinner",
        clarifying_question="Bạn muốn đổi cho ngày nào ạ?",
    )
    patcher = _mock_extraction(extraction)
    history_patcher = _mock_no_history()
    try:
        with patch("src.agents.nodes.rescheduling_node.report_routine_deviation") as mock_tool:
            mock_tool.ainvoke = AsyncMock()
            result = await handle_reschedule_request("thứ 5 tôi ăn tối lúc 9 giờ", "patient-1")
    finally:
        patcher.stop()
        history_patcher.stop()

    assert result.status == "needs_clarification"
    mock_tool.ainvoke.assert_not_called()


@pytest.mark.asyncio
async def test_tool_raising_is_contained_and_never_claims_success():
    """authorize_patient_write hoặc lỗi mạng ném exception ra ngoài tool —
    lượt chat không được vỡ, và cũng không được báo thành công."""
    extraction = RoutineDeviationExtraction(event="routine_deviation", anchor="dinner", new_time="21:00")
    patcher = _mock_extraction(extraction)
    history_patcher = _mock_no_history()
    try:
        with patch("src.agents.nodes.rescheduling_node.report_routine_deviation") as mock_tool:
            mock_tool.ainvoke = AsyncMock(side_effect=RuntimeError("not authorized"))
            result = await handle_reschedule_request("tối nay tôi ăn lúc 9 giờ", "patient-1")
    finally:
        patcher.stop()
        history_patcher.stop()

    assert result.status == "failed"
    assert "vẫn giữ nguyên" in result.message


@pytest.mark.asyncio
async def test_routine_deviation_without_new_time_is_treated_as_unclear():
    """Phòng trường hợp LLM gắn nhầm event=routine_deviation nhưng lại quên
    new_time -- vẫn phải hỏi lại, không được gọi tool với giờ rỗng."""
    extraction = RoutineDeviationExtraction(event="routine_deviation", anchor="lunch", new_time=None)
    patcher = _mock_extraction(extraction)
    history_patcher = _mock_no_history()
    try:
        with patch("src.agents.nodes.rescheduling_node.report_routine_deviation") as mock_tool:
            mock_tool.ainvoke = AsyncMock()
            result = await handle_reschedule_request("ăn trưa hơi trễ", "patient-1")
    finally:
        patcher.stop()
        history_patcher.stop()

    assert result.status == "needs_clarification"
    mock_tool.ainvoke.assert_not_called()


@pytest.mark.asyncio
async def test_out_of_scope_request_is_refused_not_rescheduled():
    extraction = RoutineDeviationExtraction(event="out_of_scope")
    patcher = _mock_extraction(extraction)
    try:
        with patch("src.agents.nodes.rescheduling_node.report_routine_deviation") as mock_tool:
            mock_tool.ainvoke = AsyncMock()
            result = await handle_reschedule_request("bỏ cữ tối luôn được không", "patient-1")
    finally:
        patcher.stop()

    assert result.status == "refused"
    assert "bác sĩ" in result.message.lower()
    mock_tool.ainvoke.assert_not_called()


@pytest.mark.asyncio
async def test_dose_change_request_is_refused():
    extraction = RoutineDeviationExtraction(event="out_of_scope")
    patcher = _mock_extraction(extraction)
    try:
        with patch("src.agents.nodes.rescheduling_node.report_routine_deviation") as mock_tool:
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
    mock_get_llm.return_value.with_structured_output.return_value.ainvoke = AsyncMock(side_effect=RuntimeError("boom"))
    try:
        with patch("src.agents.nodes.rescheduling_node.report_routine_deviation") as mock_tool:
            mock_tool.ainvoke = AsyncMock()
            result = await handle_reschedule_request("hôm nay tôi ăn trưa muộn", "patient-1")
    finally:
        patcher.stop()

    assert result.status == "needs_clarification"
    mock_tool.ainvoke.assert_not_called()


@pytest.mark.asyncio
async def test_busy_window_no_conflicting_doses():
    extraction = RoutineDeviationExtraction(
        event="busy_window",
        busy_start="14:00",
        busy_end="17:00",
        target_day="today",
    )
    patcher = _mock_extraction(extraction)
    try:
        with patch("src.agents.nodes.rescheduling_node.get") as mock_get:
            mock_get.return_value = {
                "patient_id": "patient-1",
                "date": "2026-08-29",
                "timezone": "Asia/Ho_Chi_Minh",
                "doses": [
                    {
                        "scheduled_dose_id": "d1",
                        "medication_name": "Metformin",
                        "dose_slot": "Sáng",
                        "current_scheduled_at": "2026-08-29T01:00:00Z",  # 08:00 VN
                        "status": "PENDING",
                    }
                ],
            }
            result = await handle_reschedule_request(
                "chiều nay bận họp từ 14h đến 17h", "patient-1", client_date="2026-08-29"
            )
    finally:
        patcher.stop()

    assert result.status == "needs_clarification"
    assert "không có cữ thuốc nào" in result.message


@pytest.mark.asyncio
async def test_busy_window_with_conflicting_dose_asks_replacement_time():
    extraction = RoutineDeviationExtraction(
        event="busy_window",
        busy_start="14:00",
        busy_end="17:00",
        target_day="today",
    )
    patcher = _mock_extraction(extraction)
    try:
        with patch("src.agents.nodes.rescheduling_node.get") as mock_get:
            mock_get.return_value = {
                "patient_id": "patient-1",
                "date": "2026-08-29",
                "timezone": "Asia/Ho_Chi_Minh",
                "doses": [
                    {
                        "scheduled_dose_id": "d1",
                        "medication_name": "Amlodipine 5mg",
                        "dose_slot": "Trưa",
                        "current_scheduled_at": "2026-08-29T08:00:00Z",  # 15:00 VN -> falls in 14:00-17:00
                        "status": "PENDING",
                    }
                ],
            }
            result = await handle_reschedule_request(
                "chiều nay bận họp từ 14h đến 17h", "patient-1", client_date="2026-08-29"
            )
    finally:
        patcher.stop()

    assert result.status == "needs_clarification"
    assert "Amlodipine 5mg" in result.message
    assert "14:00 - 17:00" in result.message
    assert "mấy giờ" in result.message


@pytest.mark.asyncio
async def test_busy_window_schedule_lookup_failure_does_not_claim_no_doses():
    extraction = RoutineDeviationExtraction(
        event="busy_window",
        busy_start="14:00",
        busy_end="17:00",
        target_day="today",
    )
    patcher = _mock_extraction(extraction)
    try:
        with patch("src.agents.nodes.rescheduling_node.get", new=AsyncMock(side_effect=RuntimeError("timeout"))):
            result = await handle_reschedule_request(
                "chiều nay bận họp từ 14h đến 17h",
                "patient-1",
                client_date="2026-08-29",
            )
    finally:
        patcher.stop()

    assert result.status == "failed"
    assert "chưa kiểm tra được lịch" in result.message
    assert "không có cữ thuốc nào" not in result.message


@pytest.mark.asyncio
async def test_busy_window_requires_client_date_before_checking_schedule():
    extraction = RoutineDeviationExtraction(
        event="busy_window",
        busy_start="14:00",
        busy_end="17:00",
        target_day="today",
    )
    patcher = _mock_extraction(extraction)
    try:
        with patch("src.agents.nodes.rescheduling_node.get") as mock_get:
            result = await handle_reschedule_request("chiều nay bận họp từ 14h đến 17h", "patient-1")
    finally:
        patcher.stop()

    assert result.status == "failed"
    mock_get.assert_not_called()


@pytest.mark.asyncio
async def test_busy_window_crossing_midnight_checks_the_next_day_too():
    extraction = RoutineDeviationExtraction(
        event="busy_window",
        busy_start="22:00",
        busy_end="02:00",
        target_day="today",
    )
    patcher = _mock_extraction(extraction)
    try:
        with patch("src.agents.nodes.rescheduling_node.get") as mock_get:
            mock_get.side_effect = [
                {
                    "patient_id": "patient-1",
                    "date": "2026-08-29",
                    "timezone": "Asia/Ho_Chi_Minh",
                    "doses": [],
                },
                {
                    "patient_id": "patient-1",
                    "date": "2026-08-30",
                    "timezone": "Asia/Ho_Chi_Minh",
                    "doses": [
                        {
                            "scheduled_dose_id": "d1",
                            "medication_name": "Melatonin",
                            "dose_slot": "Tối",
                            "current_scheduled_at": "2026-08-29T18:30:00Z",
                            "status": "PENDING",
                        }
                    ],
                },
            ]
            result = await handle_reschedule_request(
                "tối nay tôi bận từ 22h đến 2h sáng",
                "patient-1",
                client_date="2026-08-29",
            )
    finally:
        patcher.stop()

    assert mock_get.await_count == 2
    assert result.status == "needs_clarification"
    assert "Melatonin" in result.message
