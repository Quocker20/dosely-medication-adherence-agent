"""Deterministic, live answer for the authenticated patient's schedule today."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from langchain_core.messages import AIMessage

from src.agents.nodes.next_dose_node import format_dose_value
from src.agents.state import AgentState
from src.modules.planning.core.backend_client import BackendAPIError, get


_PATIENT_STATUS = {
    "TAKEN": "Đã uống",
    "PENDING": "Chưa uống",
    "MISSED": "Chưa uống (đã quá giờ)",
    "SKIPPED": "Chưa uống (đã bỏ qua)",
}


def _patient_status(value: object) -> str:
    status = str(value or "PENDING").upper()
    return _PATIENT_STATUS.get(status, "Chưa uống")


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
    analysis = state.get("intent_analysis") or {}
    client_date = state.get("client_date")
    date_reference = str(analysis.get("date_reference") or "").casefold()
    if client_date and date_reference in {"tomorrow", "mai", "ngày mai"}:
        try:
            client_date = (date.fromisoformat(client_date) + timedelta(days=1)).isoformat()
        except ValueError:
            pass
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

    requested_time = str(analysis.get("schedule_time") or "").strip()
    if requested_time:
        try:
            hour, minute = (int(part) for part in requested_time.split(":", 1))
            doses = [
                dose for dose in doses
                if _local_hour_minute(dose.get("current_scheduled_at"), patient_timezone) == (hour, minute)
            ]
        except (TypeError, ValueError):
            pass
    requested_statuses = {str(value).upper() for value in (analysis.get("statuses") or [])}
    if requested_statuses:
        doses = [dose for dose in doses if str(dose.get("status") or "").upper() in requested_statuses]
    asks_dose_status = "dose_status" in (analysis.get("topics") or [])
    requested_period = analysis.get("dose_period")
    if asks_dose_status:
        period_hours = {
            "morning": range(0, 12), "noon": range(11, 15),
            "evening": range(15, 24), "bedtime": range(20, 24),
        }
        allowed_hours = period_hours.get(requested_period)
        if allowed_hours is not None:
            doses = [
                dose for dose in doses
                if (_local_hour(dose.get("current_scheduled_at"), patient_timezone) in allowed_hours)
            ]
        missed = [
            dose for dose in doses
            if str(dose.get("status") or "").upper() in {"MISSED", "SKIPPED"}
        ]
        period_text = {"morning": "sáng", "noon": "trưa", "evening": "chiều/tối", "bedtime": "trước khi ngủ"}.get(requested_period, "")
        if not missed:
            return {"messages": [AIMessage(content=(
                f"Không có cữ thuốc nào được ghi nhận là bỏ lỡ hoặc bỏ qua {period_text} ngày {local_date}."
            ))]}
        lines = [f"Các cữ thuốc bị bỏ lỡ hoặc bỏ qua {period_text} ngày {local_date}:"]
        doses = missed
    else:
        lines = [f"Lịch uống thuốc ngày {local_date} của {address}:"]
    if not doses:
        detail = f" lúc {requested_time}" if requested_time else ""
        return {"messages": [AIMessage(content=f"Không tìm thấy cữ thuốc phù hợp{detail} trong lịch ngày {local_date}.")]}
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
        status = _patient_status(dose.get("status"))
        lines.append(
            f"{index}. {_format_local_time(dose.get('current_scheduled_at'), patient_timezone)} - "
            f"{dose.get('medication_name') or 'Thuốc chưa rõ tên'}{amount_text} - {status}"
        )
    return {"messages": [AIMessage(content="\n".join(lines))]}


def _local_hour(value: object, timezone_name: str | None = None) -> int:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if timezone_name and parsed.tzinfo is not None:
            parsed = parsed.astimezone(ZoneInfo(timezone_name))
        return parsed.hour
    except (TypeError, ValueError, KeyError):
        return -1


def _local_hour_minute(value: object, timezone_name: str | None = None) -> tuple[int, int] | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if timezone_name and parsed.tzinfo is not None:
            parsed = parsed.astimezone(ZoneInfo(timezone_name))
        return parsed.hour, parsed.minute
    except (TypeError, ValueError, KeyError):
        return None
