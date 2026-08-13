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

from src.modules.planning.core.backend_client import post

logger = logging.getLogger("safety")

# Từ cong_viec.md §4.1 / "Kế hoạch tầng 2" §1.2 — cố tình viết bằng ngôn
# ngữ dân dã, KHÔNG phải thuật ngữ y khoa, vì bệnh nhân nói "thở không ra
# hơi" chứ không nói "khó thở cấp". ≥40 mục theo yêu cầu kế hoạch, nhóm
# theo hệ cơ quan chỉ để dễ đọc/maintain — lúc match vẫn duyệt phẳng cả
# danh sách. Đây là danh sách khởi điểm — CẦN bác sĩ/dược sĩ trong team
# review trước khi dùng thật, việc này ngoài thẩm quyền của AI.
SEVERE_SYMPTOM_KEYWORDS: tuple[str, ...] = (
    # Hô hấp
    "khó thở",
    "thở không ra hơi",
    "thở gấp",
    "thở khò khè",
    "thở dốc",
    # Tim mạch / ngực
    "tức ngực",
    "đau ngực",
    "đau thắt ngực",
    "đè nặng ngực",
    "tim đập nhanh",
    "tim đập loạn",
    "đánh trống ngực",
    # Đột quỵ / thần kinh
    "méo miệng",
    "nói ngọng",
    "nói không rõ",
    "yếu liệt tay chân",
    "tê liệt nửa người",
    "không cử động được tay",
    "không cử động được chân",
    "co giật",
    "động kinh",
    "co cứng người",
    # Ý thức
    "ngất",
    "xỉu",
    "choáng váng ngã",
    "mất ý thức",
    "lơ mơ không tỉnh",
    "không đánh thức được",
    # Xuất huyết / tiêu hóa nặng
    "nôn ra máu",
    "đi ngoài ra máu",
    "đại tiện ra máu",
    "phân đen",
    "ho ra máu",
    "chảy máu không cầm được",
    # Dị ứng nặng
    "phát ban",
    "nổi mẩn khắp người",
    "nổi mề đay",
    "sưng mặt",
    "sưng môi",
    "sưng lưỡi",
    "sưng họng khó nuốt",
    # Đau/sốt dữ dội
    "đau bụng dữ dội",
    "đau đầu dữ dội",
    "đau đầu như búa bổ",
    "sốt cao không hạ",
    # Sức khỏe tâm thần / quá liều — quan trọng với bệnh nhân cao tuổi
    # đang dùng nhiều thuốc, KHÔNG được bỏ sót nhóm này
    "muốn chết",
    "không muốn sống nữa",
    "tự tử",
    "uống nhầm thuốc quá liều",
    "uống quá liều thuốc",
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
    """Gửi alert bằng cách dùng chung API SOS của hệ thống.
    Đại diện cho bệnh nhân tạo tín hiệu khẩn cấp khi phát hiện qua chat.
    """
    message = f"[{severity}] {reason} (Bằng chứng: {evidence})"
    return await post(
        f"/patients/{patient_id}/sos",
        json={"message": message, "metadata": {"source": "agent_auto_detect"}},
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
