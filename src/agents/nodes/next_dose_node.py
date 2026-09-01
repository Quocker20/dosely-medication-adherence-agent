"""Deterministic next-dose answer from the schedule displayed by the app."""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

from langchain_core.messages import AIMessage

from src.agents.state import AgentState
from src.modules.planning.core.backend_client import BackendAPIError, get
from src.rag_retrieval.service import fold

_CLOCK_TIME = re.compile(r"\b(?P<hour>[01]?\d|2[0-3])\s*(?::|h|giờ)\s*(?P<minute>[0-5]\d)?\b", re.I)


def _last_user_text(state: AgentState) -> str:
    for message in reversed(state.get("messages") or []):
        content = getattr(message, "content", None)
        if content is not None and message.__class__.__name__ in {"HumanMessage", "HumanMessageChunk"}:
            return str(content)
    return ""


def _requested_date_and_time(state: AgentState) -> tuple[str | None, tuple[int, int] | None, bool]:
    text = _last_user_text(state)
    normalized = fold(text)
    base_raw = state.get("client_date")
    target = str(base_raw) if base_raw else None
    is_future_date = False
    if any(marker in normalized.split() for marker in ("mai", "tomorrow")) and base_raw:
        try:
            target = (date.fromisoformat(str(base_raw)) + timedelta(days=1)).isoformat()
            is_future_date = True
        except ValueError:
            pass
    match = _CLOCK_TIME.search(text)
    requested_time = (int(match.group("hour")), int(match.group("minute") or 0)) if match else None
    return target, requested_time, is_future_date


def _dose_local_time(dose: dict, timezone_name: str | None) -> tuple[int, int] | None:
    try:
        parsed = datetime.fromisoformat(str(dose.get("current_scheduled_at", "")).replace("Z", "+00:00"))
        if timezone_name and parsed.tzinfo is not None:
            parsed = parsed.astimezone(ZoneInfo(timezone_name))
        return parsed.hour, parsed.minute
    except (TypeError, ValueError, KeyError):
        return None


def _format_time(value: str, timezone_name: str | None = None) -> str:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if timezone_name and parsed.tzinfo is not None:
            parsed = parsed.astimezone(ZoneInfo(timezone_name))
        return parsed.strftime("%H:%M")
    except (TypeError, ValueError, KeyError):
        return value


def format_dose_value(value: object) -> str:
    if value in (None, ""):
        return ""
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return str(value).strip()
    rendered = format(number.normalize(), "f")
    return "0" if rendered == "-0" else rendered


def _is_not_before(dose: dict, client_now: datetime) -> bool:
    try:
        scheduled = datetime.fromisoformat(str(dose.get("current_scheduled_at", "")).replace("Z", "+00:00"))
        return scheduled >= client_now
    except (TypeError, ValueError):
        return False


async def next_dose_node(state: AgentState) -> dict:
    patient_id = state.get("patient_id")
    address = state.get("patient_address", "bạn")
    addressed = address.capitalize()
    client_date, requested_time, is_future_date = _requested_date_and_time(state)
    if not patient_id:
        return {"messages": [AIMessage(content="Không xác định được tài khoản bệnh nhân.")]}
    try:
        schedule = await get(
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

    local_date = (schedule or {}).get("date", client_date or "hôm nay")
    timezone_name = (schedule or {}).get("timezone")
    doses = (schedule or {}).get("doses", [])
    if not doses:
        return {
            "messages": [AIMessage(content=f"{addressed} chưa có lịch uống thuốc nào được tạo cho ngày {local_date}.")]
        }

    pending = [dose for dose in doses if str(dose.get("status", "")).upper() == "PENDING"]
    client_now_raw = state.get("client_datetime")
    if client_now_raw and not is_future_date:
        try:
            client_now = datetime.fromisoformat(client_now_raw.replace("Z", "+00:00"))
            pending = [dose for dose in pending if _is_not_before(dose, client_now)]
        except (TypeError, ValueError):
            pending = []
    if requested_time is not None:
        pending = [dose for dose in pending if _dose_local_time(dose, timezone_name) == requested_time]
    pending.sort(key=lambda dose: str(dose.get("current_scheduled_at", "")))

    if not pending and requested_time is not None:
        rendered = f"{requested_time[0]:02d}:{requested_time[1]:02d}"
        reply = f"{addressed} không có cữ thuốc đang chờ lúc {rendered} trong lịch ngày {local_date}."
    elif not pending:
        reply = (
            f"{addressed} có lịch thuốc trong ngày {local_date}, nhưng hiện không còn cữ nào sắp tới. "
            "Các cữ hôm nay đã hoàn tất, đã bỏ qua hoặc đã quá giờ."
        )
    else:
        dose = pending[0]
        amount = " ".join(
            str(value).strip()
            for value in (format_dose_value(dose.get("dose_value")), dose.get("dose_unit"))
            if value not in (None, "")
        )
        amount_text = f", liều {amount}" if amount else ""
        reply = (
            f"Cữ tiếp theo của {address} là {dose.get('medication_name', 'thuốc chưa rõ tên')} "
            f"lúc {_format_time(str(dose.get('current_scheduled_at', '')), timezone_name)}{amount_text}."
        )
    return {"messages": [AIMessage(content=reply)]}
