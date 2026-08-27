"""Deterministic next-dose answer backed by the authenticated patient API."""

from __future__ import annotations

from datetime import datetime

from langchain_core.messages import AIMessage

from src.agents.state import AgentState
from src.modules.planning.core.backend_client import BackendAPIError, get


def _format_time(value: str) -> str:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).strftime("%H:%M")
    except (TypeError, ValueError):
        return value


async def next_dose_node(state: AgentState) -> dict:
    """Explain the structured next-dose state without asking the LLM to infer a date."""
    try:
        result = await get("/patients/me/schedules/next")
    except BackendAPIError:
        return {
            "messages": [
                AIMessage(
                    content=(
                        "Mình chưa thể kết nối tới dữ liệu lịch thuốc lúc này. "
                        "Vui lòng thử lại sau hoặc kiểm tra trực tiếp mục Lịch uống thuốc."
                    )
                )
            ]
        }

    status = (result or {}).get("status")
    local_date = (result or {}).get("local_date", "hôm nay")
    if status == "NO_SCHEDULE":
        reply = f"Bạn chưa có lịch uống thuốc nào được tạo cho ngày {local_date}."
    elif status == "NO_UPCOMING":
        reply = (
            f"Bạn có lịch thuốc trong ngày {local_date}, nhưng hiện không còn cữ nào sắp tới. "
            "Các cữ hôm nay đã hoàn tất, đã bỏ qua hoặc đã quá giờ."
        )
    elif status == "UPCOMING" and (result or {}).get("dose"):
        dose = result["dose"]
        amount = " ".join(
            str(value).strip()
            for value in (dose.get("dose_value"), dose.get("dose_unit"))
            if value not in (None, "")
        )
        amount_text = f", liều {amount}" if amount else ""
        reply = (
            f"Cữ tiếp theo của bạn là {dose.get('medication_name', 'thuốc chưa rõ tên')} "
            f"lúc {_format_time(str(dose.get('current_scheduled_at', '')))}{amount_text}."
        )
    else:
        reply = "Dữ liệu lịch thuốc trả về không hợp lệ. Vui lòng thử lại sau."
    return {"messages": [AIMessage(content=reply)]}
