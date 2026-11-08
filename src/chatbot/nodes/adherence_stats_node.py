"""Deterministic, read-only answer for how well the patient took medicines recently."""

from __future__ import annotations

import logging
from datetime import date, timedelta

from langchain_core.messages import AIMessage

from src.chatbot.clients.backend_client import get
from src.chatbot.state import AgentState

logger = logging.getLogger(__name__)

_WINDOW_DAYS = 7
_ERROR_REPLY = (
    "Mình chưa thể lấy dữ liệu tuân thủ dùng thuốc lúc này. "
    "Vui lòng thử lại sau hoặc xem trực tiếp mục Lịch sử uống thuốc."
)


def _end_date(client_date: object) -> date:
    try:
        return date.fromisoformat(str(client_date))
    except ValueError:
        return date.today()


async def adherence_stats_node(state: AgentState) -> dict:
    patient_id = state.get("patient_id")
    if not patient_id:
        return {"messages": [AIMessage(content="Không xác định được tài khoản bệnh nhân.")]}
    end = _end_date(state.get("client_date") or date.today().isoformat())
    start = end - timedelta(days=_WINDOW_DAYS - 1)
    try:
        result = await get(
            f"/patients/{patient_id}/adherence",
            params={"from": start.isoformat(), "to": end.isoformat()},
        )
        total = int(result["total_doses"])
        taken = int(result["taken_doses"])
        rate = float(result["adherence_rate"])
        missed = int(result.get("missed_doses") or 0)
        skipped = int(result.get("skipped_doses") or 0)
    except Exception as exc:  # noqa: BLE001 - never surface backend text to the patient
        logger.warning("adherence_stats_failed error_type=%s", type(exc).__name__)
        return {"messages": [AIMessage(content=_ERROR_REPLY)]}

    period = f"từ {start.strftime('%d/%m')} đến {end.strftime('%d/%m')}"
    if total <= 0:
        return {"messages": [AIMessage(content=f"Chưa có cữ thuốc nào được ghi nhận {period}.")]}
    percent = round(rate * 100) if rate <= 1 else round(rate)
    text = f"Trong 7 ngày qua ({period}), bạn đã uống {taken}/{total} cữ thuốc, đạt {percent}%."
    extras = []
    if missed:
        extras.append(f"{missed} cữ bị bỏ lỡ")
    if skipped:
        extras.append(f"{skipped} cữ bỏ qua")
    if extras:
        text += " Trong đó có " + " và ".join(extras) + "."
    return {"messages": [AIMessage(content=text)]}
