"""READ-ONLY tools — patient prescriptions, routine, schedule, adherence.

See cong_viec.md §2.1. Endpoints follow api-contract.md Slice 4/5/6/7.
"""

from __future__ import annotations

import json

from langchain_core.tools import tool

from src.modules.planning.core.backend_client import BackendAPIError, get


@tool
async def get_current_medications() -> str:
    """Lấy các thuốc đang dùng từ đơn đã duyệt của bệnh nhân đang đăng nhập.

    Không nhận patient_id: backend luôn suy ra danh tính từ access token để
    tránh đọc nhầm hoặc làm lộ dữ liệu của bệnh nhân khác.
    """
    try:
        result = await get("/patients/me/medications/current")
    except BackendAPIError as e:
        return f"Không lấy được danh sách thuốc hiện tại: {e.detail}"
    return json.dumps(result, ensure_ascii=False, default=str)


@tool
async def get_prescriptions(patient_id: str) -> str:
    """Lấy danh sách đơn thuốc (kèm các cữ thuốc) của bệnh nhân.

    Args:
        patient_id: Mã UUID của bệnh nhân

    Returns:
        Danh sách đơn thuốc dạng JSON string, hoặc thông báo lỗi
    """
    try:
        page = await get(f"/patients/{patient_id}/prescriptions")
    except BackendAPIError as e:
        return f"Không lấy được đơn thuốc: {e.detail}"
    return str(page.get("content", page))


@tool
async def get_patient_profile(patient_id: str) -> str:
    """Lấy hồ sơ và khung giờ sinh hoạt của bệnh nhân đang đăng nhập.

    Args:
        patient_id: Mã UUID của bệnh nhân trong phiên chat hiện tại.

    Returns:
        JSON gồm profile (name, dob, sex, timezone, emergency_note) và routine
        (wake_time, breakfast_time, lunch_time, dinner_time, sleep_time), hoặc
        thông báo lỗi.
    """
    try:
        profile = await get("/patients/me/profile")
    except BackendAPIError as e:
        return f"Không lấy được hồ sơ bệnh nhân: {e.detail}"
    if not isinstance(profile, dict):
        return "Không lấy được hồ sơ bệnh nhân: phản hồi không hợp lệ"
    profile_data = profile.get("profile", {})
    if not isinstance(profile_data, dict):
        return "Không lấy được hồ sơ bệnh nhân: phản hồi không hợp lệ"
    actual_patient_id = str(profile_data.get("user_id", ""))
    if actual_patient_id and actual_patient_id != patient_id:
        return "Không lấy được hồ sơ bệnh nhân: patient_id không khớp với phiên hiện tại"
    return json.dumps(profile, ensure_ascii=False, default=str)


@tool
async def get_scheduled_doses(patient_id: str, date: str) -> str:
    """Lấy lịch uống thuốc (các cữ cụ thể) của bệnh nhân trong một ngày.

    Args:
        patient_id: Mã UUID của bệnh nhân
        date: Ngày cần xem lịch, định dạng YYYY-MM-DD

    Returns:
        Danh sách các cữ thuốc trong ngày dạng JSON string, hoặc thông báo lỗi
    """
    try:
        schedule = await get(f"/patients/{patient_id}/schedules", params={"date": date})
    except BackendAPIError as e:
        return f"Không lấy được lịch uống thuốc: {e.detail}"
    return str(schedule.get("doses", schedule))


@tool
async def get_adherence_stats(patient_id: str, date_from: str, date_to: str) -> str:
    """Lấy thống kê tỷ lệ tuân thủ điều trị của bệnh nhân trong một khoảng thời gian.

    Args:
        patient_id: Mã UUID của bệnh nhân
        date_from: Ngày bắt đầu thống kê, định dạng YYYY-MM-DD
        date_to: Ngày kết thúc thống kê, định dạng YYYY-MM-DD

    Returns:
        Thống kê tuân thủ (adherence_rate, total_doses, taken_doses,
        skipped_doses, missed_doses) dạng JSON string, hoặc thông báo lỗi
    """
    try:
        summary = await get(
            f"/patients/{patient_id}/adherence",
            params={"from": date_from, "to": date_to},
        )
    except BackendAPIError as e:
        return f"Không lấy được thống kê tuân thủ: {e.detail}"
    return str(summary)
