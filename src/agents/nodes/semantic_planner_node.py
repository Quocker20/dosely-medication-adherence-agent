"""LLM semantic understanding: select one allowlisted, single-purpose tool."""
from __future__ import annotations

from langchain_core.messages import HumanMessage

from src.agents.semantic_plan import SemanticPlan, TOOL_TO_LEGACY_INTENT
from src.agents.state import AgentState
from src.modules.planning.core.llm import get_llm

_CLEAN_PROMPT = """
Bạn lập kế hoạch ngữ nghĩa cho RemindRx, không trả lời người dùng. Tạo 1–3 bước,
mỗi bước chỉ một tool. Câu hỏi có giờ/ngày và hỏi thuốc nào cần uống luôn dùng
get_schedule; hỏi công dụng của thuốc tham chiếu bằng giờ/cữ dùng
resolve_prescribed_medication; thuốc nêu tên trực tiếp dùng search_drug_information.
Câu hỏi liều kế tiếp dùng get_next_dose; danh sách thuốc dùng get_current_medications;
triệu chứng mới dùng record_adverse_event; thiếu dữ kiện dùng clarify; ngoài phạm vi
dùng general_response. Không đoán tên thuốc, không tạo endpoint/patient_id, không quá 3 bước.
"""

_PROMPT = """Bạn là bộ lập kế hoạch ngữ nghĩa cho RemindRx. Không trả lời người dùng.
Tạo từ 1 đến tối đa 3 bước. Mỗi bước chỉ chọn đúng MỘT tool và trích xuất tham số
từ TIN NHẮN CUỐI, có dùng ngữ cảnh gần nhất. Không tách một nhiệm vụ thống nhất
thành nhiều bước kỹ thuật; ví dụ xác định thuốc theo cữ rồi tra Dược thư vẫn là một
bước resolve_prescribed_medication.

Tool:
- get_schedule: tìm cữ/lịch theo ngày, giờ, buổi hoặc trạng thái.
- get_next_dose: cữ sắp tới gần nhất.
- get_current_medications: danh sách thuốc trong đơn hiện tại.
- explain_current_medications: giải thích toàn bộ thuốc trong đơn.
- resolve_prescribed_medication: xác định một thuốc trong đơn bằng giờ/cữ/ngữ cảnh rồi giải thích.
- search_drug_information: tra thông tin một thuốc được nêu tên trực tiếp.
- report_meal_shift: báo thay đổi giờ ăn có thể ảnh hưởng lịch.
- record_adverse_event: người dùng đang KỂ rằng họ gặp triệu chứng/tác dụng không mong muốn; trích symptoms. Không dùng cho câu hỏi chung "thuốc có tác dụng phụ gì".
- get_recent_adverse_event: người dùng tham chiếu triệu chứng vừa báo như "vẫn còn bị vậy", "triệu chứng lúc nãy" mà không mô tả một sự kiện mới.
- clarify: mục đích hoặc tham số quan trọng còn thiếu.
- general_response: chào hỏi/hướng dẫn RemindRx hợp lệ không cần dữ liệu.

Quy tắc:
- “17h nay có thuốc gì?” -> get_schedule, không phải resolve_prescribed_medication.
- “thuốc cữ 17h có tác dụng gì?” -> resolve_prescribed_medication.
- Chỉ nêu tên thuốc -> clarify và hỏi muốn biết công dụng/cách dùng/tác dụng phụ gì.
- Không tự tạo patient_id, endpoint hay câu lệnh database.
- Các nhiệm vụ độc lập được tách thành steps theo thứ tự step_1, step_2, step_3.
- Không tạo quá 3 steps. Không lặp cùng tool với cùng tham số.
- Yêu cầu đổi liều/ngừng thuốc/đổi điều trị: requested_action=change_treatment.
- Yêu cầu thay đổi lịch: requested_action=change_schedule.
"""


def _conversation(state: AgentState, limit: int = 8) -> str:
    lines = []
    for message in list(state.get("messages") or [])[-limit:]:
        role = "Người dùng" if isinstance(message, HumanMessage) else "Trợ lý"
        lines.append(f"{role}: {message.content}")
    return "\n".join(lines)


async def semantic_planner_node(state: AgentState) -> dict:
    try:
        planner = get_llm(temperature=0).with_structured_output(SemanticPlan)
        plan = await planner.ainvoke([
            {"role": "system", "content": _CLEAN_PROMPT},
            {"role": "user", "content": _conversation(state)},
        ])
    except Exception:
        return {"semantic_plan": {}, "semantic_plan_valid": False, "use_legacy_classifier": True}

    payload = plan.model_dump()
    first = plan.steps[0]
    intent = TOOL_TO_LEGACY_INTENT[first.tool] if len(plan.steps) == 1 else "multi_tool"
    analysis = {
        "intent": intent,
        "reference_type": first.drug_reference_type,
        "drug_name": first.drug_name,
        "symptoms": [item.model_dump() for item in first.symptoms],
        "schedule_time": first.schedule_time,
        "dose_period": first.dose_period,
        "statuses": first.statuses,
        "date_reference": first.date_reference,
        "topics": first.topics,
        "requested_action": first.requested_action,
        "needs_clarification": first.needs_clarification,
        "confidence": plan.confidence,
        "parser": "semantic_planner",
    }
    return {"semantic_plan": payload, "intent": intent, "intent_analysis": analysis, "use_legacy_classifier": False}
