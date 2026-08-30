"""Deterministic final boundary for every non-fixed chatbot response."""
from __future__ import annotations

import re

from langchain_core.messages import AIMessage

from src.agents.state import AgentState

_SAFE_FALLBACK = (
    "Mình chưa thể cung cấp câu trả lời này một cách an toàn. Vui lòng kiểm tra "
    "trực tiếp đơn/lịch trên RemindRx hoặc hỏi bác sĩ, dược sĩ."
)
_SECRET = re.compile(r"(?:api[_ -]?key|bearer\s+[a-z0-9._-]+|system prompt|jwt_secret)", re.I)
_DANGEROUS_DIRECTIVE = re.compile(
    r"\b(?:bạn|anh|chị|bác)\s+(?:có thể|nên|hãy)\s+"
    r"(?:tăng|giảm|đổi|ngừng|dừng|bỏ|uống thêm|uống bù|uống gấp đôi|gấp đôi)\b",
    re.I,
)
_OUT_OF_SCOPE = re.compile(r"\b(?:world cup|bóng đá|chính trị|bài thơ|giá vàng)\b", re.I)
_ENGLISH_UI_LABEL = re.compile(
    r"(?im)^\s*(?:[-*•]\s*)?(?:drug|medicine|schedule|status|next dose|dose status|"
    r"taken|pending|missed|skipped|source|instructions?|result)\s*(?:[:：-]|$)"
)


def validate_patient_output(text: str) -> list[str]:
    errors: list[str] = []
    if not text.strip():
        errors.append("empty_output")
    if _SECRET.search(text):
        errors.append("secret_or_prompt_leak")
    if _DANGEROUS_DIRECTIVE.search(text):
        errors.append("unsafe_treatment_directive")
    if _OUT_OF_SCOPE.search(text):
        errors.append("out_of_scope_output")
    if _ENGLISH_UI_LABEL.search(text):
        errors.append("english_patient_facing_label")
    if "�" in text:
        errors.append("encoding_corruption")
    return errors


async def output_guard_node(state: AgentState) -> dict:
    messages = state.get("messages", [])
    text = str(messages[-1].content) if messages else ""
    errors = validate_patient_output(text)
    if not errors:
        return {"output_guarded": True, "output_errors": []}
    return {
        "messages": [AIMessage(content=_SAFE_FALLBACK)],
        "output_guarded": False,
        "output_errors": errors,
    }
