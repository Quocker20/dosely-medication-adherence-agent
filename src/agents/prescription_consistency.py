"""Fail-closed consistency checks for patient-specific medication instructions."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

_SLOT_FIELD = {
    "MORNING": "morning_dose",
    "NOON": "noon_dose",
    "EVENING": "evening_dose",
    "BEDTIME": "bedtime_dose",
}


def _decimal(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value)).normalize()
    except (InvalidOperation, ValueError):
        return None


def _identity(item: dict[str, Any]) -> str:
    return str(item.get("medication_id") or item.get("display_name") or "").strip().casefold()


def validate_prescription_schedule(medications: list[dict[str, Any]], doses: list[dict[str, Any]]) -> list[str]:
    """Return patient-readable reasons why instructions must not be presented."""
    issues: list[str] = []
    by_item: dict[str, dict[str, Any]] = {}
    identities: dict[str, int] = {}

    for item in medications:
        name = str(item.get("display_name") or "Thuốc chưa rõ tên")
        item_id = str(item.get("id") or item.get("prescription_item_id") or "")
        identity = _identity(item)
        identities[identity] = identities.get(identity, 0) + 1
        if not item_id:
            issues.append(f"{name}: thiếu mã dòng thuốc trong đơn")
        else:
            by_item[item_id] = item
        if not str(item.get("dose_unit") or "").strip():
            issues.append(f"{name}: đơn chưa ghi đơn vị liều")
        if not str(item.get("route") or "").strip():
            issues.append(f"{name}: đơn chưa ghi đường dùng")
        meal_relation = str(item.get("meal_relation") or "").upper()
        if meal_relation and meal_relation not in {"BEFORE_MEAL", "AFTER_MEAL", "WITH_MEAL"}:
            issues.append(f"{name}: đơn có hướng dẫn bữa ăn không hợp lệ")
        prescribed = [_decimal(item.get(field)) for field in _SLOT_FIELD.values()]
        if not any(value is not None and value > 0 for value in prescribed):
            issues.append(f"{name}: đơn chưa có liều hợp lệ theo buổi")

    for identity, count in identities.items():
        if identity and count > 1:
            sample = next(item for item in medications if _identity(item) == identity)
            issues.append(f"{sample.get('display_name', 'Một thuốc')}: xuất hiện nhiều lần trong các đơn còn hiệu lực")

    seen_slots: set[tuple[str, str]] = set()
    for dose in doses:
        item_id = str(dose.get("prescription_item_id") or "")
        item = by_item.get(item_id)
        name = str(dose.get("medication_name") or "Thuốc chưa rõ tên")
        if item is None:
            issues.append(f"{name}: có trong lịch nhưng không thuộc đơn còn hiệu lực")
            continue
        slot = str(dose.get("dose_slot") or "").upper()
        field = _SLOT_FIELD.get(slot)
        if field is None:
            issues.append(f"{name}: lịch có buổi uống không hợp lệ")
            continue
        seen_slots.add((item_id, slot))
        expected, actual = _decimal(item.get(field)), _decimal(dose.get("dose_value"))
        if expected is None or expected <= 0 or actual != expected:
            issues.append(f"{name}: liều trong lịch không khớp liều trong đơn")
        if str(dose.get("dose_unit") or "").casefold() != str(item.get("dose_unit") or "").casefold():
            issues.append(f"{name}: đơn vị liều trong lịch không khớp đơn")
        item_meal = str(item.get("meal_relation") or "").upper()
        dose_meal = str(dose.get("meal_relation") or "").upper()
        if item_meal != dose_meal:
            issues.append(f"{name}: hướng dẫn liên quan bữa ăn trong lịch không khớp đơn")

    for item_id, item in by_item.items():
        name = str(item.get("display_name") or "Thuốc chưa rõ tên")
        for slot, field in _SLOT_FIELD.items():
            value = _decimal(item.get(field))
            if value is not None and value > 0 and (item_id, slot) not in seen_slots:
                issues.append(f"{name}: thiếu cữ {slot.casefold()} trong lịch ngày đang xem")

    return list(dict.fromkeys(issues))
