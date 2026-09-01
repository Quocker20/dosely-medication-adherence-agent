"""WRITE tool — reschedule remaining doses. See cong_viec.md §2.2.

Endpoint: POST /patients/{patient_id}/schedules/reschedule (api-contract.md
Slice 6). Note: the real RescheduleRequest DTO (schema.md §6.1) only takes
`reason` — there is no `from_time` field. The backend's Rescheduling Agent
infers "remaining doses from now" server-side; it is NOT something this
tool controls. This differs from the `from_time` param sketched in
cong_viec.md §2.2 — that sketch predates checking the real contract.

Server-side validation (per cong_viec.md §2.2 constraint) must reject any
attempt to change dosage/frequency/drug_id — this tool cannot bypass that,
it only sends `reason`.
"""

from __future__ import annotations

from langchain_core.tools import tool

from src.agents.tool_authorization import authorize_patient_write
from src.agents.tools.idempotency import dose_action_key
from src.modules.planning.core.backend_client import BackendAPIError, post


@tool
async def reschedule_remaining_doses(patient_id: str, reason: str) -> str:
    """Yêu cầu backend rải lại lịch uống thuốc còn lại trong ngày của bệnh nhân.

    Chỉ đổi THỜI GIAN các cữ còn lại trong ngày. Không đổi liều, không đổi
    số cữ, không thêm/bớt thuốc — điều này được backend validate, tool này
    không có quyền ép buộc điều đó.

    Args:
        patient_id: Mã UUID của bệnh nhân
        reason: Lý do cần rải lại lịch (ví dụ: "bệnh nhân báo dậy trễ 2 tiếng")

    Returns:
        Trạng thái yêu cầu (agent_run_id, status) dạng chuỗi, hoặc thông báo lỗi
    """
    try:
        authorize_patient_write("reschedule_remaining_doses", patient_id, intent="report_meal_shift")
        result = await post(
            f"/patients/{patient_id}/schedules/reschedule",
            json={"reason": reason},
        )
    except BackendAPIError as e:
        return f"Không rải lại được lịch: {e.detail}"
    return str(result)


# Tools return their failure as a plain string (LangChain tool results are
# strings), so callers need a marker to tell a refusal apart from a success.
# rescheduling_node matches on this rather than assuming the call worked.
DEVIATION_TOOL_FAILURE_PREFIX = "Không báo được lệch giờ:"


@tool
async def report_routine_deviation(
    patient_id: str, day_offset: int, anchor: str, overridden_time: str, reason: str
) -> str:
    """Báo lệch giờ sinh hoạt cho MỘT mốc cụ thể (breakfast/lunch/dinner/sleep).

    Chỉ dời giờ (các) cữ thuốc neo vào đúng mốc đó, CHỈ trong đúng ngày đó.
    Không đổi liều, không đổi số cữ. Nếu việc dời giờ vi phạm ràng buộc lâm
    sàng, backend trả về NEEDS_REVIEW cho bác sĩ xử lý thay vì tự đoán.

    Ngày được truyền dưới dạng ĐỘ LỆCH so với hôm nay, không phải ngày tuyệt
    đối: chỉ backend mới biết timezone của bệnh nhân, nên chỉ backend mới quy
    ra được ngày đúng.

    Args:
        patient_id: Mã UUID của bệnh nhân
        day_offset: 0 = hôm nay, 1 = ngày mai, 2 = ngày kia
        anchor: Mốc sinh hoạt bị lệch — "breakfast", "lunch", "dinner" hoặc "sleep"
        overridden_time: Giờ mới, định dạng HH:MM
        reason: Lý do bệnh nhân báo (nguyên văn hoặc diễn giải ngắn)

    Returns:
        Trạng thái yêu cầu (agent_run_id, status) dạng chuỗi, hoặc thông báo lỗi
    """
    try:
        authorize_patient_write("report_routine_deviation", patient_id, intent="report_meal_shift")
        result = await post(
            f"/patients/{patient_id}/routine-overrides",
            json={
                "day_offset": day_offset,
                "anchor": anchor,
                "overridden_time": overridden_time,
                "source": "CHAT",
                "reason": reason,
            },
        )
    except BackendAPIError as e:
        return f"{DEVIATION_TOOL_FAILURE_PREFIX} {e.detail}"
    return str(result)


@tool
async def record_dose_action(scheduled_dose_id: str, action: str, note: str = "") -> str:
    """Ghi nhận hành động uống thuốc của bệnh nhân qua đoạn chat.

    Chỉ gọi tool này khi người dùng chủ động thông báo họ đã uống thuốc,
    hoặc bỏ thuốc.

    Args:
        scheduled_dose_id: Mã UUID của cữ thuốc cần ghi nhận
        action: Hành động (TAKEN, SNOOZE, SKIPPED)
        note: Ghi chú thêm nếu có (ví dụ: lý do bỏ thuốc, ngủ quên)

    Returns:
        Kết quả ghi nhận thành công hay không
    """
    # Ownership is checked atomically by the backend endpoint. This tool is not
    # exposed to the chat LLM and must be wrapped by a confirmed dedicated flow.
    payload = {"note": note} if note else {}
    try:
        result = await post(
            f"/scheduled-doses/{scheduled_dose_id}/actions",
            json={
                "action": action.upper(),
                "action_source": "AGENT",
                "payload": payload,
            },
            headers={"Idempotency-Key": dose_action_key(scheduled_dose_id, action)},
        )
    except BackendAPIError as e:
        return f"Không ghi nhận được: {e.detail}"
    return str(result)
