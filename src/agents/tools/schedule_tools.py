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
        result = await post(
            f"/patients/{patient_id}/schedules/reschedule",
            json={"reason": reason},
        )
    except BackendAPIError as e:
        return f"Không rải lại được lịch: {e.detail}"
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
