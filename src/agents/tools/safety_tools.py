"""Red Alert safety mechanism. See cong_viec.md §4.1 — "tính năng an toàn
quan trọng nhất của sản phẩm". Two pure-code triggers plus one LLM-assisted
trigger, all funneling into `trigger_red_alert`.

IMPORTANT — send path is stubbed. api-contract.md has no endpoint for
code/agent-initiated alert creation. The closest matches are
`POST /patients/{id}/sos` (patient-initiated, TriggerSosRequest) and
`GET /alerts` (doctor-only listing) — neither fits "system detects missed
doses / severe symptom keyword and creates an alert". This is the exact gap
cong_viec.md §3 flags as unresolved. Confirm the real endpoint with the
backend team, then fill in `_send_alert` — everything else here (keyword
matching, missed-dose streak, fail-open error handling) is real, working
logic, not a stub.
"""
from __future__ import annotations

import logging

from langchain_core.tools import tool

logger = logging.getLogger("safety")

# Từ cong_viec.md §4.1 — cố tình viết bằng ngôn ngữ dân dã, KHÔNG phải
# thuật ngữ y khoa, vì bệnh nhân nói "thở không ra hơi" chứ không nói
# "khó thở cấp". Đây là danh sách khởi điểm lấy nguyên từ doc — cần bác sĩ/
# dược sĩ trong team review trước khi dùng thật, việc này ngoài thẩm quyền
# của AI.
SEVERE_SYMPTOM_KEYWORDS: tuple[str, ...] = (
    "khó thở",
    "thở không ra hơi",
    "tức ngực",
    "đau ngực",
    "phát ban",
    "nổi mẩn",
    "sưng mặt",
    "sưng môi",
    "tim đập nhanh",
    "ngất",
    "co giật",
    "nôn ra máu",
)

MISSED_DOSE_ALERT_THRESHOLD = 3


def match_severe_symptom_keyword(text: str) -> str | None:
    """Lớp 1 (rule-based, LUÔN chạy trước LLM) — khớp câu mô tả triệu chứng
    của bệnh nhân với danh sách từ khóa nguy hiểm. Thuần code, không gọi LLM,
    nên không thể bị prompt injection bypass.

    Args:
        text: Câu mô tả triệu chứng của bệnh nhân

    Returns:
        Từ khóa khớp đầu tiên, hoặc None nếu không khớp
    """
    lowered = text.lower()
    for keyword in SEVERE_SYMPTOM_KEYWORDS:
        if keyword in lowered:
            return keyword
    return None


def count_missed_dose_streak(scheduled_doses: list[dict]) -> int:
    """Trigger 1 (thuần code, không LLM) — đếm chuỗi liều bị bỏ/quá giờ liên
    tiếp gần nhất trong ngày.

    Args:
        scheduled_doses: Danh sách cữ thuốc trong ngày (từ get_scheduled_doses),
            mỗi phần tử có field "status" (TAKEN/SKIPPED/MISSED/PENDING),
            đã sắp theo thời gian tăng dần (current_scheduled_at)

    Returns:
        Số lượng liều bỏ/quá giờ liên tiếp tính từ cữ gần nhất trở về trước
    """
    streak = 0
    for dose in reversed(scheduled_doses):
        if dose.get("status") in ("SKIPPED", "MISSED"):
            streak += 1
        else:
            break
    return streak


async def _send_alert(patient_id: str, reason: str, severity: str, evidence: str) -> dict:
    """Gửi alert thật lên backend. STUB — chưa có endpoint thật, xem module
    docstring. Raise để caller (trigger_red_alert) log CRITICAL và trả về
    rõ ràng thay vì âm thầm giả vờ đã gửi thành công."""
    raise NotImplementedError(
        "Chưa có backend endpoint để code/agent tự tạo alert "
        "(api-contract.md chỉ có POST /patients/{id}/sos — do bệnh nhân tự bấm — "
        "và GET /alerts — chỉ để list). Cần xác nhận endpoint thật với backend team "
        "(xem cong_viec.md mục 3) rồi implement lại hàm này."
    )


@tool
async def trigger_red_alert(patient_id: str, reason: str, severity: str, evidence: str) -> str:
    """Kích hoạt Red Alert.

    Nguyên tắc fail-open (cong_viec.md §4.1): hàm này KHÔNG BAO GIỜ raise ra
    ngoài. Nếu gửi alert thất bại (backend lỗi, chưa có endpoint,...), vẫn
    trả về rõ ràng và log CRITICAL để con người can thiệp — thà báo lỗi rõ
    ràng còn hơn im lặng bỏ sót cảnh báo.

    Được gọi trực tiếp (KHÔNG qua LLM, để tránh prompt injection) từ:
      - Trigger 1: chuỗi bỏ liều >= 3 lần liên tiếp — xem count_missed_dose_streak
      - Trigger 2 Lớp 1: khớp từ khóa triệu chứng nguy hiểm — xem match_severe_symptom_keyword
      - Trigger 3: nút SOS bấm trực tiếp
    Hoặc được LLM gọi (Lớp 2, tool này) khi câu mô tả không khớp từ khóa
    nhưng LLM đánh giá là triệu chứng nặng. LLM chỉ được BỔ SUNG — kết quả
    "không phải triệu chứng nặng" từ LLM KHÔNG được dùng để hủy alert mà
    Lớp 1 rule-based đã quyết định gửi.

    Args:
        patient_id: Mã UUID của bệnh nhân
        reason: Lý do kích hoạt (ví dụ: "MISSED_DOSES", "SEVERE_SYMPTOM: tức ngực")
        severity: Mức độ (CRITICAL/HIGH/MEDIUM)
        evidence: Bằng chứng cụ thể (câu nói của bệnh nhân, số liệu bỏ liều...)

    Returns:
        Kết quả gửi alert, hoặc thông báo lỗi rõ ràng nếu gửi thất bại
    """
    try:
        result = await _send_alert(patient_id, reason, severity, evidence)
    except Exception as e:  # noqa: BLE001 — fail-open: must never propagate
        logger.critical(
            "RED ALERT KHÔNG GỬI ĐƯỢC — patient_id=%s reason=%s severity=%s "
            "evidence=%s error=%s",
            patient_id,
            reason,
            severity,
            evidence,
            e,
        )
        return (
            f"[LỖI NGHIÊM TRỌNG] Không gửi được Red Alert tự động cho bệnh nhân "
            f"{patient_id} (lý do: {reason}, mức độ: {severity}). "
            f"Cần escalate thủ công NGAY. Chi tiết lỗi: {e}"
        )
    return f"Đã gửi Red Alert: {result}"
