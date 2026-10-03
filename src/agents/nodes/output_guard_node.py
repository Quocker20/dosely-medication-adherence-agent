"""Deterministic final boundary for every non-fixed chatbot response."""

from __future__ import annotations

import re

from langchain_core.messages import AIMessage

from src.agents.nodes.refusal_response import generate_refusal
from src.agents.state import AgentState

_SAFE_FALLBACK = (
    "Mình chưa thể cung cấp câu trả lời này một cách an toàn. Vui lòng kiểm tra "
    "trực tiếp đơn/lịch trên Dosely hoặc hỏi bác sĩ, dược sĩ."
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

_GROUNDING_REQUIRED_INTENTS = {
    "ask_drug_info",
    "ask_drug_catalog",
    "ask_prescribed_drug_info",
    "ask_scheduled_drug_info",
}


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
    # Medical knowledge answers must be grounded in the RAG/catalog result.
    # A fluent fallback from the LLM is not evidence and must never reach the
    # patient when retrieval failed or returned an unverified drug.
    if state.get("intent") in _GROUNDING_REQUIRED_INTENTS and state.get("grounding_valid") is not True:
        errors.append("missing_medical_grounding")
    refusal_reason = str(state.get("refusal_reason") or state.get("safety_reason") or "").strip()
    if state.get("scope_blocked") and not refusal_reason:
        refusal_reason = str(state.get("scope_category") or "outside_dosely_scope")
    if not refusal_reason and errors:
        # Pick one deterministic primary reason. Secondary validator findings
        # are intentionally not shown to the answer LLM.
        priority = (
            "secret_or_prompt_leak", "unsafe_treatment_directive",
            "missing_medical_grounding", "out_of_scope_output",
            "english_patient_facing_label", "encoding_corruption", "empty_output",
        )
        refusal_reason = next((item for item in priority if item in errors), errors[0])
    if not errors and not refusal_reason:
        return {"output_guarded": True, "output_errors": []}
    try:
        answer = await generate_refusal(state, refusal_reason)
        if not answer:
            raise ValueError("empty refusal")
    except Exception:
        # Fail safely if the response model is temporarily unavailable.
        answer = _SAFE_FALLBACK
    return {
        "messages": [AIMessage(content=answer)],
        "output_guarded": False,
        "output_errors": [refusal_reason],
        "refusal_reason": refusal_reason,
    }
