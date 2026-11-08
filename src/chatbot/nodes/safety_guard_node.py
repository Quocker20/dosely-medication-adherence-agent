"""safety_guard_node — Sprint 1.3 của "Kế hoạch build tầng 2 — Agent layer".

Chạy TRƯỚC LLM trò chuyện trên mọi tin nhắn, 2 lớp:

    text vào
      -> Lớp 1: rule detect (match_severe_symptom_keyword, thuần code)
             khớp -> trigger_red_alert NGAY, KHÔNG hỏi LLM, dừng ở đây
      -> Lớp 2: LLM phân loại — chỉ chạy khi Lớp 1 không khớp, timeout 3s
             LLM nói "CO" (nghiêm trọng) -> cũng trigger_red_alert
             LLM nói "KHONG", lỗi, hoặc timeout -> không escalate

Vì Lớp 2 chỉ được gọi khi Lớp 1 đã KHÔNG khớp, việc "LLM nói KHONG không
hủy được kết luận Lớp 1" được đảm bảo bằng cấu trúc luồng (không có
nhánh nào Lớp 2 chạy sau khi Lớp 1 đã kết luận escalate), không phải bằng
if/else có thể viết sai.

Khi escalated=True, graph phải NGẮT không đi tiếp vào agent_node bình
thường — trả thẳng câu trả lời cố định. Xem cách graph.py nối node này.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from src.chatbot.clients.llm import get_llm
from src.chatbot.medication_policy import fold, match_medication_decision
from src.chatbot.nodes.scope_guard_node import needs_scope_llm, prefetch_scope
from src.chatbot.state import AgentState
from src.chatbot.tools.safety_tools import (
    dispatch_red_alert,
    match_severe_symptom_keyword,
    severity_for_keyword,
)

_LLM_TIMEOUT_SECONDS = 3.0

_CLASSIFY_PROMPT = (
    "Bạn là bộ lọc an toàn y tế. Đọc câu nói của bệnh nhân dưới đây và trả lời "
    "DUY NHẤT một từ: 'CO' nếu câu mô tả triệu chứng sức khỏe nghiêm trọng/khẩn "
    "cấp (kể cả diễn đạt dân dã, không chuẩn y khoa), hoặc 'KHONG' nếu không "
    "phải. Không giải thích gì thêm, không thêm từ nào khác.\n\nCâu nói: {text}"
)

CALL_115_SENTENCE = "Nếu nguy hiểm tức thời, hãy gọi cấp cứu 115 ngay."

_FIXED_SAFE_REPLY = (
    "Các dấu hiệu bạn mô tả có thể là tình huống khẩn cấp. "
    "Hãy bấm giữ nút Cảnh báo khẩn cấp (Alert) trên màn hình để gửi thông báo cho bác sĩ. "
    + CALL_115_SENTENCE
)

_SEMANTIC_EMERGENCY_PROMPT = """Bạn là bộ phân loại cấp cứu y tế. Trả về urgent, confidence và reason theo schema.
CO chỉ khi người bệnh đang mô tả dấu hiệu nguy hiểm cần xử trí ngay: khó thở, ngất, co giật,
đau ngực dữ dội, sưng môi/lưỡi/họng, nôn ra máu, chảy máu không cầm, ý định tự sát,
uống quá liều hoặc triệu chứng tăng nhanh/nghiêm trọng.
KHONG với câu hỏi kiến thức, giả định, hoặc triệu chứng đơn lẻ chưa có dấu hiệu nặng như đau bụng,
buồn nôn, chóng mặt, đau đầu, ngứa, khô miệng, mệt, bầm tím. Không chẩn đoán.
Tin nhắn gần đây của người bệnh (cũ -> mới; tin cuối là tin cần đánh giá):
{text}"""

_MEDICATION_POLICY_REPLY = (
    "Mình chỉ hỗ trợ tra cứu thông tin về một thuốc hoặc hoạt chất cụ thể, "
    "không thể lựa chọn, kê hoặc gợi ý thuốc điều trị cho bạn. Bạn vui lòng "
    "hỏi bác sĩ/dược sĩ để được tư vấn phù hợp."
)


@dataclass
class SafetyVerdict:
    escalated: bool
    blocked: bool = False
    reason: str | None = None
    fixed_reply: str | None = None
    # Only set when escalated: CRITICAL/HIGH and which layer detected it.
    severity: str | None = None
    detector: str | None = None


class EmergencyAssessment(BaseModel):
    urgent: bool
    confidence: float = Field(ge=0, le=1)
    reason: str


async def _classify_with_llm(text: str) -> bool:
    try:
        llm = get_llm(temperature=0).with_structured_output(EmergencyAssessment)
        assessment = await asyncio.wait_for(
            llm.ainvoke([SystemMessage(content=_SEMANTIC_EMERGENCY_PROMPT.format(text=text))]),
            timeout=_LLM_TIMEOUT_SECONDS,
        )
    except Exception:  # noqa: BLE001 — Lớp 2 lỗi/timeout thì bỏ qua, không chặn luồng
        return False
    if not (assessment.urgent and assessment.confidence >= 0.9):
        return False
    # LLM-only escalation requires an independent verification pass. Explicit
    # deterministic emergency rules above still trigger immediately.
    verify_prompt = (
        "Xác minh nghiêm ngặt một cảnh báo cấp cứu. Triệu chứng nhẹ đơn lẻ như chóng mặt, "
        "buồn nôn, đau đầu, đau bụng, ngứa hoặc mệt không phải cấp cứu nếu không có dấu hiệu "
        "nặng đi kèm. Trả về urgent=true chỉ khi tin nhắn thể hiện nguy hiểm tức thời.\n"
        f"Tin nhắn gần đây:\n{text}\nKết luận lần một: {assessment.model_dump()}"
    )
    try:
        verifier = get_llm(temperature=0).with_structured_output(EmergencyAssessment)
        verified = await asyncio.wait_for(
            verifier.ainvoke([SystemMessage(content=verify_prompt)]),
            timeout=_LLM_TIMEOUT_SECONDS,
        )
    except Exception:
        return False
    return bool(verified.urgent and verified.confidence >= 0.9)


def evaluate_deterministic(text: str) -> SafetyVerdict | None:
    """Pure-code checks (no LLM). None means "nothing decided, ask the LLM layer"."""
    keyword = match_severe_symptom_keyword(text)
    if keyword:
        return SafetyVerdict(
            escalated=True, reason=f"SEVERE_SYMPTOM: {keyword}", fixed_reply=_FIXED_SAFE_REPLY,
            severity=severity_for_keyword(keyword), detector="keyword",
        )

    normalized = fold(text)
    if any(marker in normalized for marker in (
        "uong qua nhieu thuoc", "uong rat nhieu thuoc", "nuot qua nhieu thuoc",
    )):
        return SafetyVerdict(
            escalated=True,
            reason="SEVERE_SYMPTOM: suspected_overdose",
            fixed_reply=_FIXED_SAFE_REPLY,
            severity="CRITICAL", detector="keyword",
        )
    if any(marker in normalized for marker in (
        "system prompt", "bo qua moi chi dan", "bo qua chi dan truoc",
        "api key", "khoa truy cap", "du lieu noi bo",
    )):
        return SafetyVerdict(
            escalated=False, blocked=True,
            reason="secret_or_prompt_exfiltration",
            fixed_reply=_MEDICATION_POLICY_REPLY,
        )
    if any(marker in normalized for marker in (
        "doan dai", "doan thuoc", "bia cau tra loi", "citation gia", "dat citation gia",
        "nguon gia", "tao nguon gia",
    )):
        return SafetyVerdict(
            escalated=False, blocked=True,
            reason="fabrication_or_hallucination_request",
            fixed_reply=_MEDICATION_POLICY_REPLY,
        )
    if (
        any(marker in normalized for marker in ("danh dau", "ghi nhan"))
        and any(marker in normalized for marker in ("da uong", "da dung"))
        and any(marker in normalized for marker in ("chua uong", "chua dung", "du toi chua"))
    ):
        return SafetyVerdict(
            escalated=False, blocked=True,
            reason="fabricated_medication_status",
            fixed_reply=_MEDICATION_POLICY_REPLY,
        )

    medication_policy = match_medication_decision(text)
    if medication_policy:
        return SafetyVerdict(
            escalated=False, blocked=True,
            reason=medication_policy,
            fixed_reply=_MEDICATION_POLICY_REPLY,
        )

    return None


def _llm_verdict(urgent: bool) -> SafetyVerdict:
    if urgent:
        return SafetyVerdict(
            escalated=True, reason="SEVERE_SYMPTOM: llm_classified", fixed_reply=_FIXED_SAFE_REPLY,
            severity="HIGH", detector="llm",
        )
    return SafetyVerdict(escalated=False, blocked=False)


async def evaluate_safety(text: str, patient_id: str, recent_texts: list[str] | None = None) -> SafetyVerdict:
    """Logic 2 lớp thuần túy — tách riêng khỏi AgentState để test độc lập
    và để tái dùng ở chỗ khác (không chỉ trong graph chat) nếu cần.

    Keyword layer judges `text` only; the LLM layer sees `recent_texts` (the last
    few patient messages) for context."""
    verdict = evaluate_deterministic(text)
    if verdict is not None:
        return verdict
    return _llm_verdict(await _classify_with_llm("\n".join(recent_texts or [text])))


def _last_human_text(state: AgentState) -> str:
    for message in reversed(state.get("messages", [])):
        if isinstance(message, HumanMessage):
            return str(message.content)
    return ""


def _recent_human_texts(state: AgentState, limit: int = 3) -> list[str]:
    texts = [str(m.content) for m in state.get("messages", []) if isinstance(m, HumanMessage)]
    return texts[-limit:]


async def safety_guard_node(state: AgentState) -> dict:
    """Node LangGraph — xem graph.py: chạy trước agent_node trên mọi turn."""
    text = _last_human_text(state)
    scope_prefetch: dict | None = None

    verdict = evaluate_deterministic(text)
    if verdict is None:
        # Deterministic checks found nothing: run the emergency LLM layer and the
        # scope LLM classification concurrently (scope_guard reuses the latter).
        recent = "\n".join(_recent_human_texts(state) or [text])
        if needs_scope_llm(state):
            urgent, scope_prefetch = await asyncio.gather(_classify_with_llm(recent), prefetch_scope(state))
        else:
            urgent = await _classify_with_llm(recent)
        verdict = _llm_verdict(urgent)
        if verdict.escalated:
            scope_prefetch = None  # emergency wins; scope result is discarded

    if verdict.escalated or verdict.blocked:
        notified = False
        if verdict.escalated:
            # Never raises; False when unauthorized or the send failed.
            notified, _ = await dispatch_red_alert(
                state.get("patient_id", ""),
                verdict.reason or "SEVERE_SYMPTOM",
                verdict.severity or "HIGH",
                text,
                conversation_id=state.get("conversation_id"),
                detector=verdict.detector,
                use_gate=True,
            )
        return {
            # Emergency fail-safe; the graph's output_guard normally rewrites
            # this through the contextual refusal-response LLM.
            "messages": [AIMessage(content=verdict.fixed_reply)],
            "escalated": verdict.escalated,
            "safety_blocked": verdict.blocked,
            "safety_reason": verdict.reason or "",
            "refusal_reason": verdict.reason or "medical_safety_risk",
            "red_alert_notified": notified,
            "scope_prefetch": None,
        }
    return {
        "escalated": False,
        "safety_blocked": False,
        "red_alert_notified": False,
        "scope_prefetch": scope_prefetch,
    }
