"""compute_schedule — deterministic Planning Agent core. See
docs/ai_agent_scope.md §3 item 3 and cong_viec.md §1 row 2 / §4.7: this is
the piece that turns `frequency` (morning/noon/evening/bedtime_dose) +
patient routine into concrete clock times. Pure code, NO LLM call — an LLM
should never be asked to guess dose times.

Not wired into `src/agents/graph.py` — that graph is the patient-facing
chat agent (agent_type=CHAT). This function belongs to a different, not-yet-
built trigger path: the async Planning/Rescheduling Agent job described in
schema.md §6 (`agent_type=PLANNING_AGENT`, triggered by
`PRESCRIPTION_APPROVED`/`ROUTINE_UPDATED`). Wiring that trigger is a
separate piece of work — see cong_viec.md §3 open question 1.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

# Mỗi slot liều gắn với một mốc giờ sinh hoạt. Không có fallback ngầm nếu
# routine thiếu mốc giờ tương ứng — thà báo lỗi rõ ràng còn hơn tự đoán giờ
# uống thuốc sai (xem cong_viec.md §4.3 tinh thần "grounding, không bịa").
_SLOTS: tuple[tuple[str, str], ...] = (
    ("morning_dose", "breakfast_time"),
    ("noon_dose", "lunch_time"),
    ("evening_dose", "dinner_time"),
    ("bedtime_dose", "sleep_time"),
)

# Bù trừ theo meal_relation. Con số 30 phút là giá trị khởi điểm hợp lý,
# CẦN dược sĩ/bác sĩ review trước khi dùng thật — không phải kết luận y khoa.
_MEAL_OFFSET_MINUTES = 30


def _parse_time(value: Any) -> time:
    if isinstance(value, time):
        return value
    if isinstance(value, str):
        return time.fromisoformat(value)
    raise TypeError(f"Không parse được giờ sinh hoạt từ giá trị: {value!r}")


def _parse_date(value: Any) -> date:
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        return date.fromisoformat(value)
    raise TypeError(f"Không parse được ngày từ giá trị: {value!r}")


def _anchor_datetime(
    target_date: date, anchor_time: time, meal_relation: str | None, tz: ZoneInfo
) -> datetime:
    dt = datetime.combine(target_date, anchor_time, tzinfo=tz)
    if meal_relation == "BEFORE_MEAL":
        dt -= timedelta(minutes=_MEAL_OFFSET_MINUTES)
    elif meal_relation == "AFTER_MEAL":
        dt += timedelta(minutes=_MEAL_OFFSET_MINUTES)
    return dt


def _is_active_on(item: Mapping[str, Any], target_date: date) -> bool:
    start = _parse_date(item["start_date"])
    end = item.get("end_date")
    if start > target_date:
        return False
    if end is not None and _parse_date(end) < target_date:
        return False
    return True


def _enforce_minimum_interval(doses: list[dict], minimum_interval_minutes: int | None) -> None:
    """Nếu 2 cữ CÙNG một prescription_item trong ngày sát nhau hơn
    minimum_interval_minutes, đẩy cữ sau ra xa cho đủ khoảng cách. Mutates
    `doses` in place (đã sort theo thời gian tăng dần trước khi gọi)."""
    if not minimum_interval_minutes:
        return
    min_gap = timedelta(minutes=minimum_interval_minutes)
    for prev, curr in zip(doses, doses[1:]):
        prev_dt = datetime.fromisoformat(prev["current_scheduled_at"])
        curr_dt = datetime.fromisoformat(curr["current_scheduled_at"])
        gap = curr_dt - prev_dt
        if gap < min_gap:
            curr_dt = prev_dt + min_gap
            curr["current_scheduled_at"] = curr_dt.isoformat()
            curr["adjusted_for_min_interval"] = True


def compute_schedule(
    prescription_items: Sequence[Mapping[str, Any]],
    routine: Mapping[str, Any],
    target_date: date | str,
    timezone: str = "Asia/Ho_Chi_Minh",
) -> list[dict]:
    """Sinh lịch uống thuốc cụ thể trong một ngày từ đơn thuốc + lịch sinh hoạt.

    Args:
        prescription_items: danh sách item (PrescriptionItemDetailResponse-shape)
        routine: dict routine (PatientRoutineResponse-shape)
        target_date: ngày cần sinh lịch
        timezone: IANA timezone của bệnh nhân (cong_viec.md §4.7 — phải
            timezone-aware, không dùng giờ naive)

    Returns:
        Danh sách dose dict, JSON-serializable, sort theo current_scheduled_at.
        Mỗi item độc lập — KHÔNG kiểm tra tương tác giữa các thuốc khác nhau
        (Clinical Guardrails/DDI ngoài phạm vi MVP, xem cong_viec.md §1.1).

    Raises:
        ValueError: nếu item có liều ở slot mà routine thiếu mốc giờ tương ứng.
    """
    tz = ZoneInfo(timezone)
    target = _parse_date(target_date)
    all_doses: list[dict] = []

    for item in prescription_items:
        if not _is_active_on(item, target):
            continue

        item_doses: list[dict] = []
        for dose_field, anchor_field in _SLOTS:
            amount = item.get(dose_field)
            if not amount:
                continue

            anchor_raw = routine.get(anchor_field)
            if not anchor_raw:
                raise ValueError(
                    f"Thuốc '{item.get('display_name')}' cần liều {dose_field} "
                    f"nhưng routine không có {anchor_field}."
                )

            scheduled_at = _anchor_datetime(
                target, _parse_time(anchor_raw), item.get("meal_relation"), tz
            )
            item_doses.append(
                {
                    "prescription_item_id": item.get("id"),
                    "medication_name": item["display_name"],
                    "dose_amount": amount,
                    "dose_unit": item.get("dose_unit"),
                    "slot": dose_field.removesuffix("_dose"),
                    "meal_relation": item.get("meal_relation"),
                    "original_scheduled_at": scheduled_at.isoformat(),
                    "current_scheduled_at": scheduled_at.isoformat(),
                    "status": "PENDING",
                    "snooze_count": 0,
                    "instructions": item.get("instructions"),
                }
            )

        item_doses.sort(key=lambda d: d["current_scheduled_at"])
        _enforce_minimum_interval(item_doses, item.get("minimum_interval_minutes"))
        all_doses.extend(item_doses)

    all_doses.sort(key=lambda d: d["current_scheduled_at"])
    return all_doses
