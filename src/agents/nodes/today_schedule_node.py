"""Deterministic, live answer for the authenticated patient's schedule today."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
import re


def _resolve_weekday_reference(reference: str, base: date) -> date | None:
    """Resolve Vietnamese weekday references without trusting an LLM date."""
    text = str(reference or "").casefold().strip()
    names = {"2": 0, "hai": 0, "3": 1, "ba": 1, "4": 2, "tư": 2, "tu": 2,
             "5": 3, "năm": 3, "nam": 3, "6": 4, "sáu": 4, "sau": 4,
             "7": 5, "bảy": 5, "bay": 5}
    match = re.search(r"thứ\s*([234567]|hai|ba|tư|tu|năm|nam|sáu|sau|bảy|bay)\s+(?:tuần\s+)?(trước|truoc|sau|tới|toi|này)", text)
    if not match:
        return None
    monday = base - timedelta(days=base.weekday())
    week_offset = -7 if match.group(2) in {"trước", "truoc"} else (7 if match.group(2) in {"sau", "tới", "toi"} else 0)
    return monday + timedelta(days=week_offset + names[match.group(1)])


def _resolve_relative_date(reference: str, base: date) -> date | None:
    """Resolve past and future relative dates from the server's local date."""
    value = str(reference or "").casefold().strip()
    offsets = {
        "hôm qua": -1, "hom qua": -1, "yesterday": -1,
        "hôm kia": -2, "hom kia": -2,
        "day_before_yesterday": -2,
        "hôm nay": 0, "hom nay": 0, "today": 0,
        "ngày mai": 1, "ngay mai": 1, "mai": 1, "tomorrow": 1,
        "ngày mốt": 2, "ngay mot": 2, "ngày kia": 2, "ngay kia": 2,
        "day_after_tomorrow": 2,
    }
    offset = offsets.get(value)
    return base + timedelta(days=offset) if offset is not None else None

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
    pending = (state.get("memory_context") or {}).get("pending_schedule_request")
    future_reference = date_reference in {"tomorrow", "mai", "ngày mai", "day_after_tomorrow", "ngày mốt", "ngày kia"} or bool(analysis.get("target_date"))
    target_date = analysis.get("target_date") or client_date
    if client_date:
        try:
            base_date = date.fromisoformat(str(client_date))
            resolved = _resolve_weekday_reference(date_reference, base_date) or _resolve_relative_date(date_reference, base_date)
            if resolved:
                target_date = resolved.isoformat()
                future_reference = resolved > base_date
        except ValueError:
            pass
    if not analysis.get("target_date") and len(date_reference) == 10 and date_reference[4] == "-":
        try:
            parsed_reference = date.fromisoformat(date_reference)
            if client_date and parsed_reference > date.fromisoformat(client_date):
                target_date = parsed_reference.isoformat()
                future_reference = True
        except ValueError:
            pass
    if client_date and date_reference in {"tomorrow", "mai", "ngày mai"}:
        try:
            target_date = (date.fromisoformat(client_date) + timedelta(days=1)).isoformat()
        except ValueError:
            pass
    elif client_date and date_reference in {"day_after_tomorrow", "ngày mốt", "ngày kia"}:
        try:
            target_date = (date.fromisoformat(client_date) + timedelta(days=2)).isoformat()
        except ValueError:
            pass
    if pending and pending.get("target_date"):
        target_date = pending["target_date"]
    if future_reference and target_date and not pending:
        return {"messages": [AIMessage(content=(
            f"Trước khi xem lịch ngày {target_date}, bạn xác nhận giúp mình: ngày đó lịch sinh hoạt có bình thường không, không có chuyến đi hoặc việc bận nào cần tránh giờ uống thuốc chứ?"
        ))], "metadata": {"pending_schedule_request": {"target_date": target_date, "date_reference": date_reference, "stage": "confirm_routine"}}}
    if pending and pending.get("stage") == "confirm_routine":
        confirmation = str(analysis.get("confirmation_state") or "unclear")
        action = str(analysis.get("requested_action") or "read")
        if confirmation not in {"confirmed", "denied"} and action != "change_schedule":
            return {"messages": [AIMessage(content="Bạn cho mình biết ngày đó sinh hoạt bình thường hay có khung giờ bận cụ thể để mình lấy hoặc điều chỉnh lịch cho đúng nhé.")], "metadata": {"pending_schedule_request": pending}}
        if action == "change_schedule" or confirmation == "denied":
            updated = dict(pending); updated["stage"] = "collect_busy_window"
            return {"messages": [AIMessage(content=f"Ngày {target_date} bạn bận trong khung giờ nào? Bạn có muốn mình điều chỉnh lịch uống thuốc để phù hợp không?")], "metadata": {"pending_schedule_request": updated}}
    client_date = target_date
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
            ],
        }

    local_date = (result or {}).get("date", "hôm nay")
    patient_timezone = (result or {}).get("timezone")
    doses = (result or {}).get("doses", [])
    if not doses:
        return {
            "messages": [
                AIMessage(content=f"{addressed} chưa có lịch uống thuốc nào được tạo cho ngày {local_date}.")
            ],
            "metadata": {"clear_pending_schedule_request": True},
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
    return {"messages": [AIMessage(content="\n".join(lines))], "metadata": {"clear_pending_schedule_request": True}}


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
