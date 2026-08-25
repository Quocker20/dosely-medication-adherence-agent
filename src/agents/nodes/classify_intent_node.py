"""classify_intent_node — Sprint 6 của "Kế hoạch build tầng 2 — Agent layer".

Chạy SAU safety_guard_node (đã lọc triệu chứng nặng trên MỌI input rồi —
xem graph.py), nên KHÔNG có nhãn "report_symptom" riêng ở đây như sketch
gốc trong kế hoạch: report_symptom đã được xử lý xong trước khi tới node
này, không cần phân loại lại.

"report_meal_shift" đi riêng tới rescheduling_node vì đây là nhánh có ràng
buộc HITL cấu trúc cứng. "ask_drug_info" đi riêng tới SafeDrugRAG để mọi
câu trả lời thông tin thuốc bắt buộc retrieval, citation và grounding. Các
nhãn còn lại mới đi qua agent_node (chat ReAct loop). Nhãn cũng được lưu để
phục vụ audit log (xem src/agents/audit.py).

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

_MY_MEDICATION_PHRASES = (
    "tôi đang uống thuốc",
    "tôi đang dùng thuốc",
    "thuốc tôi đang uống",
    "thuốc tôi đang dùng",
    "thuốc hiện tại của tôi",
    "danh sách thuốc hiện tại",
    "bác sĩ đang cho tôi dùng thuốc",
    "bác sĩ kê cho tôi thuốc",
    "what medicines am i taking",
    "what medications am i taking",
    "my current medications",
)

_CLASSIFY_SYSTEM_PROMPT = """Phân loại tin nhắn của bệnh nhân vào ĐÚNG 1 nhãn:

- "report_meal_shift": bệnh nhân báo một bữa ăn hôm nay bị lệch giờ (ăn sớm/muộn hơn thường lệ)
- "ask_schedule": hỏi về lịch uống thuốc, đã uống thuốc chưa, cữ tiếp theo lúc nào
- "ask_my_medications": hỏi danh sách thuốc bản thân đang được kê/đang sử dụng
- "ask_drug_info": hỏi thông tin về một loại thuốc (công dụng, cách dùng...)
- "general": mọi trường hợp khác (chào hỏi, hỏi chung, yêu cầu đổi liều/ngưng thuốc, v.v.)

Chỉ trả về đúng nhãn, không giải thích."""


class IntentClassification(BaseModel):
    intent: Literal[
        "report_meal_shift", "ask_schedule", "ask_my_medications", "ask_drug_info", "general"
    ] = Field(
        description="Nhãn ý định của tin nhắn — xem hướng dẫn."
    )


def _last_human_text(state: AgentState) -> str:
    for message in reversed(state.get("messages", [])):
        if isinstance(message, HumanMessage):
            return str(message.content)
    return ""


async def classify_intent_node(state: AgentState) -> dict:
    text = _last_human_text(state)
    normalized = " ".join(text.casefold().split())
    asks_about_own_current_medicines = (
        "thuốc" in normalized
        and "tôi" in normalized
        and any(
            marker in normalized
            for marker in ("đang uống", "đang dùng", "hiện tại", "danh sách", "bác sĩ")
        )
    )
    if asks_about_own_current_medicines or any(
        phrase in normalized for phrase in _MY_MEDICATION_PHRASES
    ):
        return {"intent": "ask_my_medications"}
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
