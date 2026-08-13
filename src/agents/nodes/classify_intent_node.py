"""classify_intent_node — Sprint 6 của "Kế hoạch build tầng 2 — Agent layer".

Chạy SAU safety_guard_node (đã lọc triệu chứng nặng trên MỌI input rồi —
xem graph.py), nên KHÔNG có nhãn "report_symptom" riêng ở đây như sketch
gốc trong kế hoạch: report_symptom đã được xử lý xong trước khi tới node
này, không cần phân loại lại.

Chỉ "report_meal_shift" có route riêng (-> rescheduling_node), vì đó là
nhánh duy nhất có ràng buộc HITL cần cấu trúc cứng (xem rescheduling_node.py
— chỉ event="meal_shift" có new_time cụ thể mới được đụng tới tool). Các
nhãn còn lại (ask_schedule/ask_drug_info/general) đều route chung vào
agent_node (chat ReAct loop): nó đã có sẵn CHAT_TOOLS
(get_scheduled_doses, search_drug_info...) để tự xử lý — viết thêm handler
riêng cho từng nhãn đó chỉ là trùng lặp logic tool-calling đã có (YAGNI).
Nhãn vẫn được giữ lại trong state để phục vụ audit log (xem
src/agents/audit.py), không chỉ để routing.

LLM phân loại lỗi -> mặc định "general" (fail-open về phía an toàn nhất:
để agent_node — vốn có system prompt riêng chặn HITL — xử lý, thay vì
đoán bừa route sang rescheduling).
"""
from __future__ import annotations

from typing import Literal

from langchain_core.messages import HumanMessage
from pydantic import BaseModel, Field

from src.agents.state import AgentState
from src.modules.planning.core.llm import get_llm

_CLASSIFY_SYSTEM_PROMPT = """Phân loại tin nhắn của bệnh nhân vào ĐÚNG 1 nhãn:

- "report_meal_shift": bệnh nhân báo một bữa ăn hôm nay bị lệch giờ (ăn sớm/muộn hơn thường lệ)
- "ask_schedule": hỏi về lịch uống thuốc, đã uống thuốc chưa, cữ tiếp theo lúc nào
- "ask_drug_info": hỏi thông tin về một loại thuốc (công dụng, cách dùng...)
- "general": mọi trường hợp khác (chào hỏi, hỏi chung, yêu cầu đổi liều/ngưng thuốc, v.v.)

Chỉ trả về đúng nhãn, không giải thích."""


class IntentClassification(BaseModel):
    intent: Literal["report_meal_shift", "ask_schedule", "ask_drug_info", "general"] = Field(
        description="Nhãn ý định của tin nhắn — xem hướng dẫn."
    )


def _last_human_text(state: AgentState) -> str:
    for message in reversed(state.get("messages", [])):
        if isinstance(message, HumanMessage):
            return str(message.content)
    return ""


async def classify_intent_node(state: AgentState) -> dict:
    text = _last_human_text(state)
    try:
        llm = get_llm(temperature=0).with_structured_output(IntentClassification)
        result = await llm.ainvoke(
            [
                {"role": "system", "content": _CLASSIFY_SYSTEM_PROMPT},
                {"role": "user", "content": text},
            ]
        )
        intent = result.intent
    except Exception:  # noqa: BLE001 — lỗi phân loại -> "general", để agent_node xử lý an toàn
        intent = "general"
    return {"intent": intent}
