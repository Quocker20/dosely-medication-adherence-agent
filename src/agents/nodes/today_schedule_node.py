"""Deterministic, live answer for the authenticated patient's schedule today."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from langchain_core.messages import AIMessage

from src.agents.nodes.next_dose_node import format_dose_value
from src.agents.state import AgentState
from src.modules.planning.core.backend_client import BackendAPIError, get


def _format_local_time(value: object, timezone_name: str | None = None) -> str:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if timezone_name and parsed.tzinfo is not None:
            parsed = parsed.astimezone(ZoneInfo(timezone_name))
        return parsed.strftime("%H:%M")
    except (TypeError, ValueError, KeyError):
        return str(value or "chưa rõ giờ")


async def today_schedule_node(state: AgentState) -> dict:
    """Fetch every turn from PostgreSQL through a JWT-scoped backend API."""
    patient_id = state.get("patient_id")
    address = state.get("patient_address", "bạn")
    addressed = address.capitalize()
    client_date = state.get("client_date")
    if not patient_id:
        return {"messages": [AIMessage(content="Không xác định được tài khoản bệnh nhân.")]}
    try:
        result = await get(
            f"/patients/{patient_id}/schedules",
            params={"date": client_date} if client_date else None,
        )
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

    local_date = (result or {}).get("date", "hôm nay")
    patient_timezone = (result or {}).get("timezone")
    doses = (result or {}).get("doses", [])
    if not doses:
        return {
            "messages": [
                AIMessage(content=f"{addressed} chưa có lịch uống thuốc nào được tạo cho ngày {local_date}.")
            ]
        }

    lines = [f"Lịch uống thuốc ngày {local_date} của {address}:"]
    for index, dose in enumerate(doses, start=1):
        amount = " ".join(
            part
            for part in (
                format_dose_value(dose.get("dose_value")),
                str(dose.get("dose_unit") or "").strip(),
            )
            if part
        )
        amount_text = f" — {amount}" if amount else ""
        status = str(dose.get("status") or "PENDING")
        lines.append(
            f"{index}. {_format_local_time(dose.get('current_scheduled_at'), patient_timezone)} — "
            f"{dose.get('medication_name') or 'Thuốc chưa rõ tên'}{amount_text} — {status}"
        )
    return {"messages": [AIMessage(content="\n".join(lines))]}
