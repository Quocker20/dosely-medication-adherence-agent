"""LLM-first semantic understanding for RemindRx."""
from __future__ import annotations

import asyncio

from langchain_core.messages import HumanMessage
from src.agents.semantic_plan import SemanticPlan, TOOL_TO_LEGACY_INTENT
from src.agents.state import AgentState
from src.modules.planning.core.llm import get_llm

_PROMPT = """Bạn là bộ phân tích ngữ nghĩa của RemindRx, không trả lời người dùng.
Chuyển tin nhắn cuối và ngữ cảnh gần nhất thành 1-3 bước, mỗi bước đúng một tool trong schema.
Phân loại theo ý nghĩa, không dựa vào cụm từ cố định:
- get_schedule/get_next_dose: lịch và cữ thuốc của bệnh nhân.
- get_current_medications/explain_current_medications: danh sách hoặc giải thích thuốc trong đơn hiện tại.
- resolve_prescribed_medication: xác định thuốc trong đơn qua mô tả/ngữ cảnh rồi giải thích.
- search_drug_information: kiến thức chung về thuốc được nêu tên.
- record_adverse_event: bệnh nhân khẳng định bản thân thực sự có triệu chứng; is_personal_report=true, is_hypothetical=false.
- Một báo cáo triệu chứng vẫn chỉ dùng record_adverse_event dù người dùng nói họ đang uống thuốc/thuốc trong đơn; tool này tự lấy toàn bộ thuốc liên quan, không thêm get_current_medications.
- Câu giả định hoặc hỏi thuốc có gây triệu chứng không: is_hypothetical=true, không dùng record_adverse_event.
- Có bản nháp tác dụng phụ: hiểu phản hồi theo ngữ nghĩa. Xác nhận => confirmed; phủ nhận => denied; chưa rõ => unclear và clarify.
- report_meal_shift: thay đổi bữa ăn liên quan lịch thuốc.
- clarify: thiếu dữ kiện quan trọng hoặc độ chắc chắn dưới 0.85.
- general_response: chào hỏi, hướng dẫn RemindRx hoặc ngoài phạm vi.
Không tạo patient_id, endpoint, dữ liệu thuốc, liều hoặc chẩn đoán. Không đề xuất đổi/ngừng thuốc.
Các cách diễn đạt khác nhau nhưng cùng mục đích phải ánh xạ về cùng tool."""


def _conversation(state: AgentState, limit: int = 8) -> str:
    lines = []
    for message in list(state.get("messages") or [])[-limit:]:
        role = "Người dùng" if isinstance(message, HumanMessage) else "Trợ lý"
        lines.append(f"{role}: {message.content}")
    return "\n".join(lines)


async def semantic_planner_node(state: AgentState) -> dict:
    memory = state.get("memory_context") or {}
    pending = memory.get("pending_adverse_event")
    pending_schedule = memory.get("pending_schedule_request")
    context = _conversation(state)
    if pending:
        context += f"\nBẢN NHÁP TÁC DỤNG PHỤ CHỜ XÁC NHẬN: {pending}"
    if pending_schedule:
        context += f"\nYÊU CẦU LỊCH TƯƠNG LAI CHỜ XÁC NHẬN: {pending_schedule}. Nếu người dùng xác nhận bình thường, chọn get_schedule; nếu nói bận, chọn clarify để hỏi khung giờ; chỉ đổi lịch khi đã đồng ý rõ ràng."
    try:
        planner = get_llm(temperature=0).with_structured_output(SemanticPlan)
        # Never let an upstream LLM/network stall the chat request indefinitely.
        plan = await asyncio.wait_for(
            planner.ainvoke([{"role": "system", "content": _PROMPT}, {"role": "user", "content": context}]),
            timeout=10,
        )
    except Exception:
        return {"semantic_plan": {}, "semantic_plan_valid": False, "use_legacy_classifier": True,
                "parser_degraded": True, "intent": "clarify"}

    adverse_steps = [step for step in plan.steps if step.tool == "record_adverse_event" and step.is_personal_report]
    if adverse_steps:
        plan.steps = [adverse_steps[0]]
    first = plan.steps[0]
    if plan.confidence < 0.85 or first.confidence < 0.85:
        first.tool = "clarify"
        first.needs_clarification = True
        first.clarifying_question = first.clarifying_question or "Bạn có thể nói rõ hơn điều cần tra cứu không?"
    intent = TOOL_TO_LEGACY_INTENT[first.tool] if len(plan.steps) == 1 else "multi_tool"
    analysis = {
        "intent": intent, "reference_type": first.drug_reference_type, "drug_name": first.drug_name,
        "symptoms": [item.model_dump() for item in first.symptoms],
        "is_personal_report": first.is_personal_report, "is_hypothetical": first.is_hypothetical,
        "confirmation_state": first.confirmation_state, "schedule_time": first.schedule_time,
        "target_date": first.target_date,
        "dose_period": first.dose_period, "statuses": first.statuses, "date_reference": first.date_reference,
        "topics": first.topics, "requested_action": first.requested_action,
        "needs_clarification": first.needs_clarification, "clarifying_question": first.clarifying_question,
        "confidence": min(plan.confidence, first.confidence), "parser": "semantic_planner",
    }
    return {"semantic_plan": plan.model_dump(), "intent": intent, "intent_analysis": analysis,
            "use_legacy_classifier": False, "parser_degraded": False}
