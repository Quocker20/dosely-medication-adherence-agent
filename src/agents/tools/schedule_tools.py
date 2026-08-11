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

from src.services.backend_client import BackendAPIError, post


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
