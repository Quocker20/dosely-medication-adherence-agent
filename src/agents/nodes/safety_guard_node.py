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

from src.agents.medication_policy import match_medication_decision
from src.agents.state import AgentState
from src.agents.tools.safety_tools import match_severe_symptom_keyword, trigger_red_alert
from src.modules.planning.core.llm import get_llm

_LLM_TIMEOUT_SECONDS = 3.0

_CLASSIFY_PROMPT = (
    "Bạn là bộ lọc an toàn y tế. Đọc câu nói của bệnh nhân dưới đây và trả lời "
    "DUY NHẤT một từ: 'CO' nếu câu mô tả triệu chứng sức khỏe nghiêm trọng/khẩn "
    "cấp (kể cả diễn đạt dân dã, không chuẩn y khoa), hoặc 'KHONG' nếu không "
    "phải. Không giải thích gì thêm, không thêm từ nào khác.\n\nCâu nói: {text}"
)

_FIXED_SAFE_REPLY = (
    "Mình đã ghi nhận và báo cho người thân/bác sĩ của bạn ngay bây giờ. "
    "Nếu đang trong tình huống khẩn cấp, hãy gọi cấp cứu 115 ngay."
)

_MEDICATION_POLICY_REPLY = (
    "Mình không thể quyết định thay đổi điều trị, kê thuốc hoặc xác nhận phối hợp thuốc "
    "cho bạn. Hãy giữ nguyên hướng dẫn hiện tại và liên hệ bác sĩ/dược sĩ đang theo dõi "
    "trước khi thay đổi. Nếu đã dùng khác hướng dẫn hoặc có biểu hiện bất thường, hãy "
    "cho họ biết thuốc, liều và thời điểm đã dùng."
)

@dataclass
class SafetyVerdict:
    escalated: bool
    blocked: bool = False
    reason: str | None = None
    fixed_reply: str | None = None


async def _classify_with_llm(text: str) -> bool:
    try:
        llm = get_llm(temperature=0)
        response = await asyncio.wait_for(
            llm.ainvoke([SystemMessage(content=_CLASSIFY_PROMPT.format(text=text))]),
            timeout=_LLM_TIMEOUT_SECONDS,
        )
        verdict = str(response.content).strip().upper()
    except Exception:  # noqa: BLE001 — Lớp 2 lỗi/timeout thì bỏ qua, không chặn luồng
        return False
    return verdict.startswith("CO")


async def evaluate_safety(text: str, patient_id: str) -> SafetyVerdict:
    """Logic 2 lớp thuần túy — tách riêng khỏi AgentState để test độc lập
    và để tái dùng ở chỗ khác (không chỉ trong graph chat) nếu cần."""
    keyword = match_severe_symptom_keyword(text)
    if keyword:
        reason = f"SEVERE_SYMPTOM: {keyword}"
        await trigger_red_alert.ainvoke(
            {
                "patient_id": patient_id,
                "reason": reason,
                "severity": "HIGH",
                "evidence": text,
            }
        )
        return SafetyVerdict(escalated=True, reason=reason, fixed_reply=_FIXED_SAFE_REPLY)

    medication_reason = match_medication_decision(text)
    if medication_reason:
        return SafetyVerdict(
            escalated=False,
            blocked=True,
            reason=f"MEDICATION_POLICY: {medication_reason}",
            fixed_reply=_MEDICATION_POLICY_REPLY,
        )

    if await _classify_with_llm(text):
        reason = "SEVERE_SYMPTOM: llm_classified"
        await trigger_red_alert.ainvoke(
            {
                "patient_id": patient_id,
                "reason": reason,
                "severity": "HIGH",
                "evidence": text,
            }
        )
        return SafetyVerdict(escalated=True, reason=reason, fixed_reply=_FIXED_SAFE_REPLY)

    return SafetyVerdict(escalated=False, blocked=False)


def _last_human_text(state: AgentState) -> str:
    for message in reversed(state.get("messages", [])):
        if isinstance(message, HumanMessage):
            return str(message.content)
    return ""


async def safety_guard_node(state: AgentState) -> dict:
    """Node LangGraph — xem graph.py: chạy trước agent_node trên mọi turn."""
    text = _last_human_text(state)
    verdict = await evaluate_safety(text, state.get("patient_id", ""))

    if verdict.escalated or verdict.blocked:
        return {
            "messages": [AIMessage(content=verdict.fixed_reply)],
            "escalated": verdict.escalated,
            "safety_blocked": verdict.blocked,
            "safety_reason": verdict.reason or "",
        }
    return {"escalated": False, "safety_blocked": False}
