"""Red Alert safety mechanism. See cong_viec.md §4.1 — "tính năng an toàn
quan trọng nhất của sản phẩm". Two pure-code triggers plus one LLM-assisted
trigger, all funneling into `trigger_red_alert`.

Send path goes through `POST /patients/{id}/sos` (TriggerSosRequest), which
now carries `triggered_by_type` and `severity` so an agent-detected alert is
distinguishable from a button press. api-contract.md still has no dedicated
endpoint for code-initiated alerts; sharing the SOS route is the agreed interim
(the call runs under the patient's own token, so RBAC is unchanged).

Trigger 1 (missed-dose streak) is wired: src/modules/agents/missed_dose_scan_service.py's
MissedDoseScanService calls count_missed_dose_streak below on a Celery Beat
schedule (settings.missed_dose_scan_interval_minutes). It writes alerts via
AlertRepository directly rather than through trigger_red_alert/_send_alert —
that HTTP path runs under a patient's own bearer token (see backend_client's
get_actor_token), which a scheduled background job scanning every patient
does not have.
"""

from __future__ import annotations

import asyncio
import logging
import re
import unicodedata

from langchain_core.tools import tool

import src.core.redis as core_redis
from src.chatbot.clients.backend_client import post
from src.chatbot.tool_authorization import authorize_patient_write
from src.chatbot.tools.idempotency import alert_key

logger = logging.getLogger("safety")

# Từ cong_viec.md §4.1 / "Kế hoạch tầng 2" §1.2 — cố tình viết bằng ngôn
# ngữ dân dã, KHÔNG phải thuật ngữ y khoa, vì bệnh nhân nói "thở không ra
# hơi" chứ không nói "khó thở cấp". Chia 2 bậc: CRITICAL (đe dọa tính mạng)
# và HIGH (nặng nhưng không tức thì). Đây là danh sách khởi điểm — CẦN
# bác sĩ/dược sĩ trong team review trước khi dùng thật, việc này ngoài
# thẩm quyền của AI.
CRITICAL_SYMPTOM_KEYWORDS: tuple[str, ...] = (
    # Hô hấp
    "khó thở",
    "thở không ra hơi",
    "thở gấp",
    "thở dốc",
    "không thở được",
    "không thể thở",
    "thở không nổi",
    "ngưng thở",
    # Tim mạch / ngực
    "tức ngực",
    "đau ngực",
    "đau thắt ngực",
    "đè nặng ngực",
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
    "đột quỵ",
    # Ý thức
    "ngất",
    "xỉu",
    "choáng váng ngã",
    "mất ý thức",
    "lơ mơ không tỉnh",
    "không đánh thức được",
    "bất tỉnh",
    # Xuất huyết / tiêu hóa nặng
    "nôn ra máu",
    "đi ngoài ra máu",
    "đại tiện ra máu",
    "phân đen",
    "ho ra máu",
    "chảy máu không cầm được",
    # Dị ứng nặng ở môi/lưỡi/họng
    "sưng môi",
    "sưng lưỡi",
    "sưng họng khó nuốt",
    # Sức khỏe tâm thần / quá liều — quan trọng với bệnh nhân cao tuổi
    # đang dùng nhiều thuốc, KHÔNG được bỏ sót nhóm này
    "muốn chết",
    "không muốn sống nữa",
    "tự tử",
    "uống nhầm thuốc quá liều",
    "uống quá liều thuốc",
)

HIGH_SYMPTOM_KEYWORDS: tuple[str, ...] = (
    "thở khò khè",
    "tim đập nhanh",
    "tim đập loạn",
    "đánh trống ngực",
    "phát ban",
    "nổi mẩn khắp người",
    "nổi mề đay",
    "sưng mặt",
    "đau bụng dữ dội",
    "đau đầu dữ dội",
    "đau đầu như búa bổ",
    "sốt cao không hạ",
)

SEVERE_SYMPTOM_KEYWORDS: tuple[str, ...] = CRITICAL_SYMPTOM_KEYWORDS + HIGH_SYMPTOM_KEYWORDS

# Negation words cancel a keyword when they sit right before it, optionally with
# one filler word in between ("không còn co giật", "không bị đau ngực").
_NEGATIONS = frozenset({"không", "chưa", "hết", "chẳng", "chả"})
_NEGATION_FILLERS = frozenset({"còn", "bị", "hề", "có", "thấy", "phải"})
# Multi-syllable keywords that must still be accent-exact: unaccented "tu tu"
# is just "từ từ". (Single-syllable keywords are always accent-exact too.)
_ACCENT_EXACT_ONLY = frozenset({"tự tử"})


# Sentence/clause punctuation becomes a break token so a negation ending one
# clause ("Không.") never cancels a keyword opening the next ("Đau ngực quá").
_BREAK = "|"


def _tokens(text: str) -> list[str]:
    found = re.findall(r"\w+|[.,;:!?…\n\r]", unicodedata.normalize("NFC", text).lower())
    return [t if t[0].isalnum() or t[0] == "_" else _BREAK for t in found]


def _fold_token(token: str) -> str:
    token = unicodedata.normalize("NFD", token.replace("đ", "d"))
    return "".join(ch for ch in token if unicodedata.category(ch) != "Mn")


def _has_unnegated(
    tokens: list[str], keyword_tokens: list[str], negations: frozenset[str], fillers: frozenset[str]
) -> bool:
    """True if keyword_tokens occurs at least once with no negation right before it."""
    n = len(keyword_tokens)
    for i in range(len(tokens) - n + 1):
        if tokens[i : i + n] != keyword_tokens:
            continue
        before = tokens[max(0, i - 2) : i]
        if _BREAK in before:
            before = before[before.index(_BREAK) + 1 :] if before[-1] != _BREAK else []
        negated = bool(before) and (
            before[-1] in negations or (before[-1] in fillers and len(before) == 2 and before[0] in negations)
        )
        if not negated:
            return True
    return False


def match_severe_symptom_keyword(text: str) -> str | None:
    """Lớp 1 (rule-based, LUÔN chạy trước LLM) — khớp câu mô tả triệu chứng
    của bệnh nhân với danh sách từ khóa nguy hiểm. Thuần code, không gọi LLM,
    nên không thể bị prompt injection bypass.

    Khớp theo token: phủ định ngay trước từ khóa hủy lần khớp đó; câu gõ không
    dấu chỉ khớp các từ khóa nhiều âm tiết.

    Args:
        text: Câu mô tả triệu chứng của bệnh nhân

    Returns:
        Từ khóa khớp đầu tiên, hoặc None nếu không khớp
    """
    tokens = _tokens(text)
    folded_tokens = [_fold_token(t) for t in tokens]
    folded_negations = frozenset(_fold_token(t) for t in _NEGATIONS)
    folded_fillers = frozenset(_fold_token(t) for t in _NEGATION_FILLERS)
    for keyword in SEVERE_SYMPTOM_KEYWORDS:
        kw_tokens = keyword.split()
        if _has_unnegated(tokens, kw_tokens, _NEGATIONS, _NEGATION_FILLERS):
            return keyword
        if (
            len(kw_tokens) > 1
            and keyword not in _ACCENT_EXACT_ONLY
            and _has_unnegated(
                folded_tokens, [_fold_token(t) for t in kw_tokens], folded_negations, folded_fillers
            )
        ):
            return keyword
    return None


def severity_for_keyword(keyword: str) -> str:
    """CRITICAL for the life-threatening tier, HIGH for every other keyword."""
    return "CRITICAL" if keyword in CRITICAL_SYMPTOM_KEYWORDS else "HIGH"


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


def _triggered_by_type(reason: str) -> str:
    """Map the caller's reason onto ck_alerts_triggered_by_type.

    The reason strings are the ones the three triggers already pass in
    (see trigger_red_alert's docstring); anything unrecognised falls back to
    SOS_BUTTON, the value this call used unconditionally before.
    """
    upper = reason.upper()
    if upper.startswith("SEVERE_SYMPTOM"):
        return "SEVERE_SYMPTOM"
    if upper.startswith("MISSED_DOSES"):
        return "MISSED_DOSES"
    return "SOS_BUTTON"


async def _send_alert(
    patient_id: str,
    reason: str,
    severity: str,
    evidence: str,
    *,
    conversation_id: str | None = None,
    detector: str | None = None,
) -> dict:
    """Gửi alert bằng cách dùng chung API SOS của hệ thống.
    Đại diện cho bệnh nhân tạo tín hiệu khẩn cấp khi phát hiện qua chat.

    severity và triggered_by_type đi vào đúng cột của bảng `alerts` thay vì bị
    nhét vào chuỗi `message` — bác sĩ lọc được cảnh báo do agent phát hiện tách
    khỏi cảnh báo do bệnh nhân bấm nút.
    """
    message = f"[{severity}] {reason} (Bằng chứng: {evidence})"
    triggered_by = _triggered_by_type(reason)
    metadata: dict = {"source": "agent_auto_detect"}
    if conversation_id:
        metadata["conversation_id"] = conversation_id
    if detector:
        metadata["detector"] = detector
    return await post(
        f"/patients/{patient_id}/sos",
        json={
            "message": message,
            "metadata": metadata,
            "triggered_by_type": triggered_by,
            "severity": severity,
        },
        # Keyed by category, not by the matched keyword: rewording the same
        # complaint inside the bucket replays one alert instead of paging twice.
        # Severity is part of the key so a later CRITICAL is not replayed as the earlier HIGH.
        headers={"Idempotency-Key": alert_key(patient_id, f"{triggered_by}:{severity}")},
    )


# One agent-raised alert per patient per 30 minutes (decision D07).
_GATE_TTL_SECONDS = 1800


def _gate_key(patient_id: str, severity: str) -> str:
    return f"dosely:chat:redalert:{patient_id}:{severity}"


async def _acquire_gate(patient_id: str, severity: str) -> bool:
    """True if this call may send: gate newly set, or Redis unavailable (fail-open).

    Gated per (patient, severity): CRITICAL is blocked only by a CRITICAL gate, HIGH by
    either, so an escalation from HIGH to CRITICAL still reaches the doctor."""
    try:
        client = await core_redis.get_redis_client()
        if severity != "CRITICAL" and await client.exists(_gate_key(patient_id, "CRITICAL")):
            return False
        return bool(await client.set(_gate_key(patient_id, severity), "1", nx=True, ex=_GATE_TTL_SECONDS))
    except Exception as e:  # noqa: BLE001 — backend dedupe still protects against duplicates
        logger.warning("Red Alert gate unavailable, sending anyway error=%s", type(e).__name__)
        return True


async def _release_gate(patient_id: str, severity: str) -> None:
    """Free the gate after a failed send so the next turn can retry (short, best effort)."""
    try:
        client = await core_redis.get_redis_client()
        await asyncio.wait_for(client.delete(_gate_key(patient_id, severity)), timeout=1.0)
    except Exception:  # noqa: BLE001, S110 — best effort
        pass


async def dispatch_red_alert(
    patient_id: str,
    reason: str,
    severity: str,
    evidence: str,
    *,
    conversation_id: str | None = None,
    detector: str | None = None,
    use_gate: bool = False,
) -> tuple[bool, object]:
    """Authorize and send one Red Alert. Never raises; returns (ok, result).

    With use_gate=True (chat path), a recent alert for this patient turns the call
    into a no-op that still reports ok=True: the doctor has already been notified.
    """
    gated = False
    try:
        authorize_patient_write("trigger_red_alert", patient_id, intent="emergency")
        if use_gate:
            if not await _acquire_gate(patient_id, severity):
                return True, None
            gated = True
        result = await _send_alert(
            patient_id, reason, severity, evidence, conversation_id=conversation_id, detector=detector
        )
    except BaseException as e:
        if gated:
            try:
                await _release_gate(patient_id, severity)
            except BaseException:  # noqa: BLE001, S110 — never mask the original exit
                pass
        if not isinstance(e, Exception):
            raise  # CancelledError etc. must propagate after the gate is released
        logger.critical(
            # No reason/evidence: both can carry the patient's own words (PHI).
            "RED ALERT KHÔNG GỬI ĐƯỢC — patient_id=%s severity=%s error=%s",
            patient_id,
            severity,
            type(e).__name__,
        )
        return False, None
    return True, result


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
    ok, result = await dispatch_red_alert(patient_id, reason, severity, evidence)
    if not ok:
        return (
            f"[LỖI NGHIÊM TRỌNG] Không gửi được Red Alert tự động cho bệnh nhân "
            f"{patient_id} (lý do: {reason}, mức độ: {severity}). "
            f"Cần escalate thủ công NGAY."
        )
    return f"Đã gửi Red Alert: {result}"
