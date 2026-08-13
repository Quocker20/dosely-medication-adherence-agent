"""rescheduling_node — Sprint 3 của "Kế hoạch build tầng 2 — Agent layer".

Bệnh nhân báo lệch giờ sinh hoạt bằng lời tự do ("hôm nay tôi ăn trưa muộn,
tầm 2 giờ chiều") -> LLM extract THÀNH THAM SỐ CÓ CẤU TRÚC (structured
output, không parse text tự do) -> code quyết định có gọi tool hay không.

QUAN TRỌNG — khác với sketch gốc trong kế hoạch: sketch giả định có một
`solver.recompute(routine_override=..., from_time=now)` chạy tại chỗ. Đối
chiếu lại api-contract.md/schema.md (xem docstring
src/agents/tools/schedule_tools.py, đã ghi chú từ trước) thì
`RescheduleRequest` thật chỉ nhận `reason` — việc tính lại giờ cụ thể cho
các cữ còn lại là "Rescheduling Agent" phía BACKEND làm, không phải agent
này. Vì vậy node này KHÔNG tự gọi compute_schedule để tính giờ mới — nó chỉ
(1) extract ý định, (2) validate ý định có nằm trong thẩm quyền hay không,
(3) nếu có thì soạn `reason` rồi gọi `reschedule_remaining_doses`, để
backend tính giờ thật. Agent tuyệt đối không tự tính giờ — giữ đúng
nguyên tắc "agent là lớp dịch, không phải lớp quyết định".

3 nhánh kết quả, LUÔN trả lời bằng đúng 1 trong 3 kiểu, không tự chế thêm:
  - "rescheduled": ý định rõ ràng, có giờ cụ thể -> đã gọi tool
  - "needs_clarification": mơ hồ ("ăn muộn" không rõ giờ) -> hỏi lại,
    KHÔNG đoán giờ cụ thể
  - "refused": vượt thẩm quyền (đổi liều, bỏ cữ, ngưng thuốc...) -> từ
    chối, hướng bác sĩ/dược sĩ — đây là ranh giới HITL (cong_viec.md §4.4),
    được đảm bảo bằng cấu trúc (chỉ event="meal_shift" mới đụng tới tool),
    không chỉ dựa vào lời dặn trong prompt
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from langchain_core.messages import AIMessage, HumanMessage
from pydantic import BaseModel, Field

from src.agents.state import AgentState
from src.agents.tools.schedule_tools import reschedule_remaining_doses
from src.services.llm import get_llm

_MEAL_VI = {"breakfast": "bữa sáng", "lunch": "bữa trưa", "dinner": "bữa tối"}

_EXTRACT_SYSTEM_PROMPT = """Bạn là bộ trích xuất thông tin cho hệ thống nhắc uống thuốc. Đọc câu nói
của bệnh nhân và phân loại theo ĐÚNG 1 trong 3 nhóm:

1. "meal_shift" — bệnh nhân báo một bữa ăn hôm nay bị lệch giờ (ăn sớm/muộn hơn thường lệ),
   VÀ có nêu giờ cụ thể (hoặc suy ra được giờ cụ thể, ví dụ "2 giờ chiều" = 14:00).
   Chỉ dùng nhãn này khi new_time xác định được rõ ràng dạng HH:MM.

2. "unclear" — bệnh nhân có ý báo lệch giờ ăn nhưng KHÔNG nêu giờ cụ thể
   (ví dụ "tôi ăn muộn", "hôm nay ăn trễ"). KHÔNG được tự đoán giờ. Thay vào
   đó viết 1 câu hỏi lại ngắn gọn, lịch sự để hỏi giờ cụ thể.

3. "out_of_scope" — bệnh nhân yêu cầu điều vượt thẩm quyền của hệ thống:
   đổi liều lượng, bỏ/ngưng một cữ thuốc, đổi thuốc, ngưng điều trị, hoặc bất
   kỳ điều gì không phải "lệch giờ bữa ăn hôm nay". Ví dụ: "bỏ cữ tối luôn",
   "tăng liều lên 2 viên", "tôi ngưng uống thuốc này được không".

Chỉ trả về đúng cấu trúc đã yêu cầu, không giải thích thêm."""


class MealShiftExtraction(BaseModel):
    event: Literal["meal_shift", "unclear", "out_of_scope"] = Field(
        description="Phân loại ý định của bệnh nhân — xem hướng dẫn."
    )
    meal: Literal["breakfast", "lunch", "dinner"] | None = Field(
        default=None, description="Bữa ăn bị lệch giờ, chỉ điền khi event=meal_shift hoặc unclear."
    )
    new_time: str | None = Field(
        default=None, description="Giờ mới dạng HH:MM (24h), CHỈ điền khi event=meal_shift."
    )
    clarifying_question: str | None = Field(
        default=None, description="Câu hỏi lại, CHỈ điền khi event=unclear."
    )


@dataclass
class RescheduleResult:
    status: Literal["rescheduled", "needs_clarification", "refused"]
    message: str


_REFUSAL_MESSAGE = (
    "Việc này ngoài phạm vi mình có thể tự quyết định — bạn vui lòng liên hệ "
    "bác sĩ hoặc dược sĩ để được tư vấn nhé."
)
_EXTRACTION_FAILED_MESSAGE = (
    "Mình chưa hiểu rõ ý bạn lắm, bạn có thể nói lại cụ thể hơn được không?"
)


async def extract_meal_shift(text: str) -> MealShiftExtraction:
    """LLM extract có schema cứng (structured output) — không parse text tự
    do. temperature=0 vì đây là phân loại, không phải sinh văn bản tự do."""
    llm = get_llm(temperature=0).with_structured_output(MealShiftExtraction)
    return await llm.ainvoke(
        [
            {"role": "system", "content": _EXTRACT_SYSTEM_PROMPT},
            {"role": "user", "content": text},
        ]
    )


async def handle_reschedule_request(text: str, patient_id: str) -> RescheduleResult:
    """Điểm vào chính của node này. Không bao giờ tự tính giờ, không bao
    giờ gọi tool cho nhánh ngoài "meal_shift" có new_time rõ ràng."""
    try:
        extraction = await extract_meal_shift(text)
    except Exception:  # noqa: BLE001 — LLM lỗi thì hỏi lại, không đoán bừa, không crash
        return RescheduleResult(status="needs_clarification", message=_EXTRACTION_FAILED_MESSAGE)

    if extraction.event == "out_of_scope":
        return RescheduleResult(status="refused", message=_REFUSAL_MESSAGE)

    if extraction.event == "unclear" or not extraction.new_time:
        question = extraction.clarifying_question or _EXTRACTION_FAILED_MESSAGE
        return RescheduleResult(status="needs_clarification", message=question)

    meal_vi = _MEAL_VI.get(extraction.meal, "bữa ăn")
    reason = f"Bệnh nhân báo {meal_vi} hôm nay dời sang {extraction.new_time} (nguyên văn: \"{text}\")"

    tool_result = await reschedule_remaining_doses.ainvoke(
        {"patient_id": patient_id, "reason": reason}
    )

    return RescheduleResult(
        status="rescheduled",
        message=(
            f"Mình đã báo hệ thống rải lại lịch uống thuốc còn lại trong hôm nay theo "
            f"{meal_vi} mới ({extraction.new_time}). {tool_result}"
        ),
    )


def _last_human_text(state: AgentState) -> str:
    for message in reversed(state.get("messages", [])):
        if isinstance(message, HumanMessage):
            return str(message.content)
    return ""


async def rescheduling_node(state: AgentState) -> dict:
    """Node LangGraph — xem graph.py: classify_intent route "report_meal_shift"
    tới đây thay vì agent_node."""
    text = _last_human_text(state)
    result = await handle_reschedule_request(text, state.get("patient_id", ""))
    return {"messages": [AIMessage(content=result.message)]}
