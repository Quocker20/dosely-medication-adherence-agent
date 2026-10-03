from __future__ import annotations
import asyncio
from typing import Literal
from langchain_core.messages import AIMessage, ToolMessage
from pydantic import BaseModel, Field
from src.agents.state import AgentState
from src.modules.planning.core.llm import get_llm

class Review(BaseModel):
    decision: Literal["approve", "reject"]
    reason: str = Field(default="")

_MEDICAL_INTENTS = {"ask_drug_info", "ask_drug_catalog", "ask_prescribed_drug_info", "ask_scheduled_drug_info"}
_FALLBACK = "Mình chưa thể xác minh đủ thông tin để trả lời an toàn. Bạn không nên tự đổi, ngừng hoặc thay thuốc; hãy giữ theo đơn hiện tại và liên hệ bác sĩ/dược sĩ. Nếu bạn gửi tên thuốc và phản ứng cụ thể, mình sẽ tra cứu nguồn phù hợp."

async def semantic_output_reviewer_node(state: AgentState) -> dict:
    if state.get("refusal_reason"):
        return {"output_reviewed": True}
    messages = state.get("messages") or []
    answer = str(messages[-1].content) if messages else ""
    intent = str(state.get("intent") or "")
    evidence = "\n".join(str(m.content) for m in messages[:-1] if isinstance(m, (ToolMessage, AIMessage)))[-12000:]
    if not answer.strip():
        return {"messages": [AIMessage(content=_FALLBACK)], "output_reviewed": False}
    if intent in _MEDICAL_INTENTS and state.get("grounding_valid") is not True:
        return {"messages": [AIMessage(content=_FALLBACK)], "output_reviewed": False}
    try:
        reviewer = get_llm(temperature=0).with_structured_output(Review)
        result = await asyncio.wait_for(reviewer.ainvoke(f"Duyệt câu trả lời Dosely. Chỉ approve nếu đúng phạm vi, không bịa, không kê đơn/đổi liều và có bằng chứng tool khi là câu hỏi thuốc. Intent: {intent}\nCâu trả lời: {answer}\nBằng chứng: {evidence}"), timeout=6)
    except Exception:
        return {"output_reviewed": True}
    if result.decision != "approve":
        return {"messages": [AIMessage(content=_FALLBACK)], "output_reviewed": False}
    return {"output_reviewed": True}
