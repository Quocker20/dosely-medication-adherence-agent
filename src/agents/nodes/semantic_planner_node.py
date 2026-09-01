"""LLM-first semantic understanding for RemindRx."""
from __future__ import annotations

import asyncio

from langchain_core.messages import HumanMessage
from src.agents.semantic_plan import SemanticPlan, TOOL_TO_LEGACY_INTENT
from src.agents.state import AgentState
from src.modules.planning.core.llm import get_llm
from src.rag_retrieval.service import fold

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


_PROMPT += "\nQUY TẮC AN TOÀN: yêu cầu tự chọn/kê liều, chọn kháng sinh, đổi hoặc ngừng thuốc (kể cả khi nói đang mang thai) phải chọn clarify với requested_action=change_treatment; không chọn multi_tool và không dùng tool tra cứu để thay tư vấn bác sĩ."

_PROMPT += """

QUY TẮC ROUTING BẮT BUỘC:
- "tôi đang dùng thuốc gì", "bác sĩ kê mấy loại": đúng MỘT bước get_current_medications.
- "giải thích/cách dùng các thuốc trong đơn": đúng MỘT bước explain_current_medications.
- Đọc liều, giờ, bữa ăn, công dụng hoặc thông tin của một thuốc trong đơn qua mô tả gián tiếp
  (lúc 7h30, buổi sáng, vừa uống, viên sắp uống, thuốc thứ hai, thuốc sau ăn): đúng MỘT bước
  resolve_prescribed_medication và đặt drug_reference_type tương ứng; không dùng search_drug_information.
- "thuốc này/viên màu trắng" mà chưa đủ định danh: chọn clarify, không out_of_scope.
- Báo đổi giờ ăn là đúng MỘT bước report_meal_shift. Thiếu giờ thì vẫn chọn report_meal_shift với
  needs_clarification=true và clarifying_question hỏi giờ; không chọn general_response.
- Lượt xác nhận ngắn phải dùng ngữ cảnh ngay trước đó: xác nhận triệu chứng => record_adverse_event;
  xác nhận sinh hoạt bình thường cho yêu cầu lịch => get_schedule.
- Không tách một mục đích đọc đơn thành nhiều bước chỉ vì câu hỏi có cả thuốc, liều, giờ hoặc bữa ăn.
"""


def _conversation(state: AgentState, limit: int = 8) -> str:
    lines = []
    for message in list(state.get("messages") or [])[-limit:]:
        role = "Người dùng" if isinstance(message, HumanMessage) else "Trợ lý"
        lines.append(f"{role}: {message.content}")
    return "\n".join(lines)


def _last_human_text(state: AgentState) -> str:
    for message in reversed(state.get("messages") or []):
        if isinstance(message, HumanMessage):
            return str(message.content)
    return ""


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

    # Stabilize explicit product references after semantic parsing. The LLM
    # still extracts topics and other fields; these unambiguous references
    # must not drift between current-medication, RAG and clarification routes.
    text = _last_human_text(state)
    normalized = fold(text)
    first = plan.steps[0]
    reference_rules = (
        (r"\b(?:luc|cu)\s*\d{1,2}(?:\s*(?:gio|h)\s*\d{0,2})?\b", "schedule_time"),
        (r"\b(?:vien|thuoc)\s+buoi\s+(?:sang|trua|toi)\b", "dose_period"),
        (r"\b(?:thuoc|vien)\s+(?:toi\s+)?vua\s+uong\b", "recent_dose"),
        (r"\b(?:vien|thuoc)\s+(?:sap|tiep theo)\s+uong\b", "next_dose"),
        (r"\bthuoc\s+thu\s+(?:hai|ba|2|3)\b", "prescription_ordinal"),
    )
    import re
    for pattern, reference_type in reference_rules:
        if re.search(pattern, normalized):
            first.tool = "resolve_prescribed_medication"
            first.drug_reference_type = reference_type
            first.needs_clarification = False
            first.confidence = max(first.confidence, 0.95)
            plan.confidence = max(plan.confidence, 0.95)
            plan.steps = [first]
            break
    if first.drug_name and first.tool in {"clarify", "general_response", "search_drug_knowledge", "search_drug_information"}:
        first.tool = "search_drug_information"
        first.drug_reference_type = "drug_name"
        first.needs_clarification = False
        first.confidence = max(first.confidence, 0.95)
        plan.confidence = max(plan.confidence, 0.95)
        plan.steps = [first]
    if not first.drug_name and any(marker in normalized for marker in (
        "thuoc nay", "vien nay", "thuoc do", "vien do",
    )) and first.drug_reference_type in {"none", "drug_name"}:
        first.tool = "clarify"
        first.needs_clarification = True
        first.clarifying_question = "Bạn vui lòng cho mình biết tên thuốc hoặc thuốc đó nằm ở cữ nào trong lịch nhé."
        first.confidence = max(first.confidence, 0.95)
        plan.confidence = max(plan.confidence, 0.95)
        plan.steps = [first]
    if any(marker in normalized for marker in ("trang thai", "da uong", "chua uong")) and any(
        marker in normalized for marker in ("cu", "lich", "gio")
    ):
        first.tool = "get_schedule"
        first.needs_clarification = False
        first.confidence = max(first.confidence, 0.95)
        plan.confidence = max(plan.confidence, 0.95)
        plan.steps = [first]
    if any(marker in normalized for marker in (
        "an sang muon", "an trua muon", "an toi muon", "doi gio an",
    )):
        first.tool = "report_meal_shift"
        first.needs_clarification = not bool(first.schedule_time)
        first.confidence = max(first.confidence, 0.95)
        plan.confidence = max(plan.confidence, 0.95)
        plan.steps = [first]
    if "lieu bac si ke" in normalized or "lieu hien tai" in normalized:
        first.tool = "explain_current_medications"
        first.needs_clarification = False
        first.confidence = max(first.confidence, 0.95)
        plan.confidence = max(plan.confidence, 0.95)
        plan.steps = [first]

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
