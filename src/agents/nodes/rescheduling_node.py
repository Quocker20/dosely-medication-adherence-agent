"""rescheduling_node — Sprint 3 của "Kế hoạch build tầng 2 — Agent layer".

Bệnh nhân báo lệch giờ sinh hoạt bằng lời tự do ("hôm nay tôi ăn trưa muộn,
tầm 2 giờ chiều", "hôm nay tôi ngủ trễ") -> LLM extract THÀNH THAM SỐ CÓ
CẤU TRÚC (structured output, không parse text tự do) -> code quyết định có
gọi tool hay không.

QUAN TRỌNG — khác với sketch gốc trong kế hoạch: sketch giả định có một
`solver.recompute(routine_override=..., from_time=now)` chạy tại chỗ. Đối
chiếu lại api-contract.md/schema.md thì việc tính lại giờ cụ thể cho (các)
cữ bị ảnh hưởng là "Rescheduling Agent" phía BACKEND làm (xem
src/modules/agents/planner.py's expand_schedule(overrides=...)), không phải
agent này. Vì vậy node này KHÔNG tự gọi compute_schedule để tính giờ mới —
nó chỉ (1) extract ý định, (2) validate ý định có nằm trong thẩm quyền hay
không, (3) nếu có thì gọi report_routine_deviation với đúng anchor+giờ đã
trích xuất, để backend tính giờ thật và validate ràng buộc lâm sàng. Agent
tuyệt đối không tự tính giờ — giữ đúng nguyên tắc "agent là lớp dịch, không
phải lớp quyết định".

4 nhánh kết quả, LUÔN trả lời bằng đúng 1 trong 4 kiểu, không tự chế thêm:
  - "rescheduled": ý định rõ ràng, có giờ cụ thể -> đã gọi tool
  - "needs_clarification": mơ hồ ("ăn muộn"/"ngủ trễ" không rõ giờ, hoặc báo
    khung giờ bận cần hỏi giờ thay thế) -> hỏi lại, KHÔNG đoán giờ cụ thể.
  - "refused": vượt thẩm quyền (đổi liều, bỏ cữ, ngưng thuốc...) -> từ
    chối, hướng bác sĩ/dược sĩ — đây là ranh giới HITL, được đảm bảo bằng
    cấu trúc (chỉ event="routine_deviation" mới đụng tới tool ghi), không
    chỉ dựa vào lời dặn trong prompt
  - "failed": ý định hợp lệ nhưng backend từ chối ghi (sai ngày, đang có
    run khác chạy, lỗi mạng...) -> nói rõ là lịch KHÔNG đổi.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from langchain_core.messages import AIMessage, HumanMessage
from pydantic import BaseModel, Field

from src.agents.state import AgentState
from src.agents.tools.patient_tools import get_recent_routine_overrides
from src.agents.tools.schedule_tools import DEVIATION_TOOL_FAILURE_PREFIX, report_routine_deviation
from src.modules.planning.core.backend_client import get
from src.modules.planning.core.llm import get_llm

_ANCHOR_VI = {"breakfast": "bữa sáng", "lunch": "bữa trưa", "dinner": "bữa tối", "sleep": "giờ ngủ"}

_EXTRACT_SYSTEM_PROMPT = """Bạn là bộ trích xuất thông tin cho hệ thống nhắc uống thuốc. Đọc câu nói
của bệnh nhân và phân loại theo ĐÚNG 1 trong 4 nhóm:

1. "routine_deviation" — bệnh nhân báo một mốc sinh hoạt bị lệch giờ
   (ăn sớm/muộn hơn thường lệ, HOẶC ngủ/thức trễ hơn thường lệ),
   VÀ có nêu giờ cụ thể (hoặc suy ra được giờ cụ thể, ví dụ "2 giờ chiều" = 14:00).
   Chỉ dùng nhãn này khi new_time xác định được rõ ràng dạng HH:MM. Điền anchor
   tương ứng: "breakfast" (bữa sáng), "lunch" (bữa trưa), "dinner" (bữa tối),
   "sleep" (giờ đi ngủ/thức khuya). Nếu bệnh nhân nói rõ "hôm nay", "mai" hoặc
   "ngày kia" thì điền target_day tương ứng; không nhắc tới ngày thì bỏ trống.

2. "busy_window" — bệnh nhân báo một khung giờ bận không thể uống thuốc
   (ví dụ "chiều nay 14h-17h bận họp", "sáng mai bận từ 8h đến 11h").
   Điền busy_start và busy_end dạng HH:MM. Điền target_day ("today", "tomorrow",
   "day_after_tomorrow") nếu có.

3. "unclear" — bệnh nhân có ý báo lệch giờ (ăn hoặc ngủ) nhưng KHÔNG nêu giờ
   cụ thể (ví dụ "tôi ăn muộn", "hôm nay ăn trễ", "tôi ngủ trễ"). KHÔNG được
   tự đoán giờ. Vẫn điền anchor nếu xác định được mốc nào (breakfast/lunch/
   dinner/sleep). Viết 1 câu hỏi lại ngắn gọn, lịch sự để hỏi giờ cụ thể.
   CŨNG dùng nhãn này khi bệnh nhân có nhắc tới ngày nhưng KHÔNG phải
   "hôm nay"/"mai"/"ngày kia" (ví dụ "thứ 5", "cuối tuần", "ngày 15",
   "tuần sau") — hỏi lại cho rõ ngày, TUYỆT ĐỐI không tự quy ra ngày.

4. "out_of_scope" — bệnh nhân yêu cầu điều vượt thẩm quyền của hệ thống:
   đổi liều lượng, bỏ/ngưng một cữ thuốc, đổi thuốc, ngưng điều trị, hoặc bất
   kỳ điều gì không phải "lệch giờ sinh hoạt". Ví dụ: "bỏ cữ tối luôn",
   "tăng liều lên 2 viên", "tôi ngưng uống thuốc này được không".

Chỉ trả về đúng cấu trúc đã yêu cầu, không giải thích thêm."""


class RoutineDeviationExtraction(BaseModel):
    event: Literal["routine_deviation", "busy_window", "unclear", "out_of_scope"] = Field(
        description="Phân loại ý định của bệnh nhân — xem hướng dẫn."
    )
    anchor: Literal["breakfast", "lunch", "dinner", "sleep"] | None = Field(
        default=None, description="Mốc sinh hoạt bị lệch, điền khi event=routine_deviation hoặc unclear."
    )
    new_time: str | None = Field(
        default=None, description="Giờ mới dạng HH:MM (24h), CHỈ điền khi event=routine_deviation."
    )
    busy_start: str | None = Field(
        default=None, description="Giờ bắt đầu khung bận dạng HH:MM (24h), CHỈ điền khi event=busy_window."
    )
    busy_end: str | None = Field(
        default=None, description="Giờ kết thúc khung bận dạng HH:MM (24h), CHỈ điền khi event=busy_window."
    )
    target_day: Literal["today", "tomorrow", "day_after_tomorrow"] | None = Field(
        default=None,
        description=(
            'Ngày áp dụng, CHỈ điền khi bệnh nhân nói rõ "hôm nay"/"mai"/"ngày kia". '
            "Bỏ trống nếu không nhắc tới ngày (mặc định hôm nay)."
        ),
    )
    clarifying_question: str | None = Field(default=None, description="Câu hỏi lại, CHỈ điền khi event=unclear.")


_DAY_OFFSETS = {"today": 0, "tomorrow": 1, "day_after_tomorrow": 2}
_DAY_VI = {0: "hôm nay", 1: "ngày mai", 2: "ngày kia"}


@dataclass
class RescheduleResult:
    status: Literal["rescheduled", "needs_clarification", "refused", "failed"]
    message: str


_REFUSAL_MESSAGE = (
    "Việc này ngoài phạm vi mình có thể tự quyết định — bạn vui lòng liên hệ bác sĩ hoặc dược sĩ để được tư vấn nhé."
)
_EXTRACTION_FAILED_MESSAGE = "Mình chưa hiểu rõ ý bạn lắm, bạn có thể nói lại cụ thể hơn được không?"


async def extract_routine_deviation(text: str) -> RoutineDeviationExtraction:
    """LLM extract có schema cứng (structured output) — không parse text tự
    do. temperature=0 vì đây là phân loại, không phải sinh văn bản tự do."""
    llm = get_llm(temperature=0).with_structured_output(RoutineDeviationExtraction)
    return await llm.ainvoke(
        [
            {"role": "system", "content": _EXTRACT_SYSTEM_PROMPT},
            {"role": "user", "content": text},
        ]
    )


async def _recent_times_for_anchor(patient_id: str, anchor: str) -> list[str]:
    """Read-only lookup, never raises — cold-start (no history yet) or any
    backend error both just mean "no suggestion", not a failure."""
    try:
        raw = await get_recent_routine_overrides.ainvoke({"patient_id": patient_id, "anchor": anchor})
        rows = json.loads(raw)
    except Exception:  # noqa: BLE001 — history is a nice-to-have, never fatal
        return []
    if not isinstance(rows, list):
        return []
    return [str(row.get("overridden_time")) for row in rows if isinstance(row, dict) and row.get("overridden_time")]


async def _draft_history_aware_question(anchor: str, recent_times: list[str], day_label: str = "hôm nay") -> str | None:
    """LLM drafts ONLY the phrasing of the clarifying question — it never
    sets new_time itself. The patient must still answer with a concrete time
    on the next turn before extract_routine_deviation can act on it."""
    if not recent_times:
        return None
    anchor_vi = _ANCHOR_VI.get(anchor, "giờ sinh hoạt")
    prompt = (
        f"Bệnh nhân báo lệch {anchor_vi} {day_label} nhưng chưa nói rõ giờ cụ thể. "
        f"Những lần gần đây họ từng báo giờ lệch: {', '.join(recent_times)}. "
        "Viết đúng 1 câu hỏi lại ngắn gọn, lịch sự bằng tiếng Việt, có thể gợi ý "
        "giờ phổ biến gần đây nhưng PHẢI hỏi xác nhận rõ ràng, không được khẳng "
        "định thay bệnh nhân. Chỉ trả về câu hỏi, không giải thích thêm."
    )
    try:
        llm = get_llm(temperature=0.3)
        response = await asyncio.wait_for(llm.ainvoke(prompt), timeout=3.0)
        content = str(response.content).strip()
        return content or None
    except Exception:  # noqa: BLE001 — fail back to the plain question, never crash the turn
        return None


def _parse_time_str(t_str: str | None) -> time | None:
    if not t_str:
        return None
    try:
        parts = t_str.strip().split(":")
        return time(int(parts[0]), int(parts[1]))
    except Exception:
        return None


def _time_in_window(value: time, start: time, end: time) -> bool:
    if start <= end:
        return start <= value <= end
    return value >= start or value <= end


async def _handle_busy_window(
    patient_id: str,
    extraction: RoutineDeviationExtraction,
    day_offset: int,
    client_date: str | None = None,
) -> RescheduleResult:
    """Xử lý khung giờ bận (Phase 4): Tra cứu lịch trong ngày đích, lọc các cữ bị trùng,
    và hỏi bệnh nhân giờ thay thế cho từng cữ. Tuyệt đối không tự ý xóa cữ hay đoán giờ."""
    day_label = _DAY_VI.get(day_offset, "hôm nay")
    start_t = _parse_time_str(extraction.busy_start)
    end_t = _parse_time_str(extraction.busy_end)
    if not start_t or not end_t:
        return RescheduleResult(
            status="needs_clarification",
            message=f"Bạn có thể cho mình biết rõ khung giờ bận {day_label} từ mấy giờ đến mấy giờ được không?",
        )

    if not client_date:
        return RescheduleResult(
            status="failed",
            message="Mình chưa xác định được ngày theo thiết bị của bạn nên chưa thể kiểm tra lịch trong khung giờ bận.",
        )

    try:
        base_d = date.fromisoformat(client_date)
    except ValueError:
        return RescheduleResult(
            status="failed",
            message="Ngày trên thiết bị không hợp lệ nên mình chưa thể kiểm tra lịch trong khung giờ bận.",
        )
    target_d = base_d + timedelta(days=day_offset)

    schedule_days = [target_d]
    if start_t > end_t:
        schedule_days.append(target_d + timedelta(days=1))

    schedule_payloads = []
    try:
        for schedule_day in schedule_days:
            schedule_data = await get(f"/patients/{patient_id}/schedules?date={schedule_day.isoformat()}")
            if isinstance(schedule_data, dict):
                schedule_payloads.append(schedule_data)
    except Exception:
        return RescheduleResult(
            status="failed",
            message="Mình chưa kiểm tra được lịch thuốc hiện tại trong khung giờ bận. Lịch uống thuốc hiện tại vẫn giữ nguyên.",
        )

    doses = [dose for payload in schedule_payloads for dose in payload.get("doses", [])]
    tz_str = next(
        (payload.get("timezone") for payload in schedule_payloads if payload.get("timezone")),
        "Asia/Ho_Chi_Minh",
    )
    tz = ZoneInfo(tz_str)

    conflicting_doses: list[dict] = []
    for d in doses:
        if d.get("status") in ("TAKEN", "SKIPPED", "CANCELLED"):
            continue
        sched_at_str = d.get("current_scheduled_at")
        if not sched_at_str:
            continue
        try:
            sched_dt = datetime.fromisoformat(sched_at_str.replace("Z", "+00:00")).astimezone(tz)
            sched_t = sched_dt.time()
            if _time_in_window(sched_t, start_t, end_t):
                conflicting_doses.append({**d, "local_time": sched_dt.strftime("%H:%M")})
        except Exception:
            continue

    if not conflicting_doses:
        return RescheduleResult(
            status="needs_clarification",
            message=(
                f"Trong khung giờ {extraction.busy_start} - {extraction.busy_end} {day_label}, "
                f"bạn không có cữ thuốc nào cần uống."
            ),
        )

    # Liệt kê các cữ thuốc và hỏi giờ dời sang
    items_desc = []
    for d in conflicting_doses:
        slot = d.get("dose_slot", "Cữ thuốc")
        med = d.get("medication_name", "thuốc")
        t_str = d.get("local_time", "")
        items_desc.append(f"{slot} ({med}) lúc {t_str}")

    doses_summary = ", ".join(items_desc)
    return RescheduleResult(
        status="needs_clarification",
        message=(
            f"Bạn có {doses_summary} rơi vào khung giờ bận {extraction.busy_start} - {extraction.busy_end} {day_label}. "
            f"Bạn dự kiến sẽ ăn hoặc uống thuốc lúc mấy giờ để mình điều chỉnh lại lịch cho bạn nhé?"
        ),
    )


async def handle_reschedule_request(text: str, patient_id: str, client_date: str | None = None) -> RescheduleResult:
    """Điểm vào chính của node này. Không bao giờ tự tính giờ, không bao
    giờ gọi tool cho nhánh ngoài 'routine_deviation' có new_time rõ ràng."""
    try:
        extraction = await extract_routine_deviation(text)
    except Exception:  # noqa: BLE001 — LLM lỗi thì hỏi lại, không đoán bừa, không crash
        return RescheduleResult(status="needs_clarification", message=_EXTRACTION_FAILED_MESSAGE)

    if extraction.event == "out_of_scope":
        return RescheduleResult(status="refused", message=_REFUSAL_MESSAGE)

    day_offset = _DAY_OFFSETS.get(extraction.target_day or "today", 0)
    day_label = _DAY_VI.get(day_offset, "hôm nay")

    if extraction.event == "busy_window":
        return await _handle_busy_window(patient_id, extraction, day_offset, client_date)

    if extraction.event == "unclear" or not extraction.new_time:
        question = extraction.clarifying_question or _EXTRACTION_FAILED_MESSAGE
        if extraction.anchor:
            recent_times = await _recent_times_for_anchor(patient_id, extraction.anchor)
            suggested = await _draft_history_aware_question(extraction.anchor, recent_times, day_label)
            if suggested:
                question = suggested
        return RescheduleResult(status="needs_clarification", message=question)

    anchor_vi = _ANCHOR_VI.get(extraction.anchor, "giờ sinh hoạt")
    reason = f'Bệnh nhân báo {anchor_vi} {day_label} dời sang {extraction.new_time} (nguyên văn: "{text}")'

    try:
        tool_result = await report_routine_deviation.ainvoke(
            {
                "patient_id": patient_id,
                "day_offset": day_offset,
                "anchor": extraction.anchor,
                "overridden_time": extraction.new_time,
                "reason": reason,
            }
        )
    except Exception as exc:
        return RescheduleResult(
            status="failed",
            message=f"Không thể cập nhật lịch {anchor_vi} {day_label}: {exc}. Lịch uống thuốc hiện tại vẫn giữ nguyên.",
        )

    if isinstance(tool_result, str) and tool_result.startswith(DEVIATION_TOOL_FAILURE_PREFIX):
        detail = tool_result.removeprefix(DEVIATION_TOOL_FAILURE_PREFIX).strip()
        return RescheduleResult(
            status="failed",
            message=f"Không thể cập nhật lịch {anchor_vi} {day_label}: {detail}. Lịch uống thuốc hiện tại vẫn giữ nguyên.",
        )

    return RescheduleResult(
        status="rescheduled",
        message=(
            f"Mình đã báo hệ thống rải lại các cữ thuốc liên quan {anchor_vi} {day_label} theo "
            f"giờ mới ({extraction.new_time}). {tool_result}"
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
    result = await handle_reschedule_request(text, state.get("patient_id", ""), state.get("client_date"))
    return {"messages": [AIMessage(content=result.message)]}
