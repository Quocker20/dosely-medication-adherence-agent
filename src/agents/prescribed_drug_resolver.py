"""Resolve indirect medication references against authenticated patient data.

This module never guesses a drug name.  It uses only the current prescription,
the same dated schedule endpoint used by the App, or a previously verified
medication stored in conversation working memory.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from zoneinfo import ZoneInfo

from src.modules.planning.core.backend_client import BackendAPIError, get


class ResolutionStatus(StrEnum):
    RESOLVED_ONE = "RESOLVED_ONE"
    RESOLVED_MULTIPLE = "RESOLVED_MULTIPLE"
    NOT_FOUND = "NOT_FOUND"
    INSUFFICIENT_REFERENCE = "INSUFFICIENT_REFERENCE"
    BACKEND_UNAVAILABLE = "BACKEND_UNAVAILABLE"
    INACTIVE_PRESCRIPTION = "INACTIVE_PRESCRIPTION"
    CONTEXT_EXPIRED = "CONTEXT_EXPIRED"


@dataclass(slots=True)
class ResolutionResult:
    status: ResolutionStatus
    medications: list[dict] = field(default_factory=list)
    reference_type: str = "none"
    reference_value: str | None = None
    schedule: dict | None = None


_PERIOD_TO_SLOT = {
    "morning": "MORNING", "noon": "NOON", "evening": "EVENING", "bedtime": "BEDTIME",
    "sáng": "MORNING", "trưa": "NOON", "chiều": "EVENING", "tối": "EVENING",
    "trước khi ngủ": "BEDTIME",
}


def _local_time(value: object, timezone_name: str | None) -> tuple[int, int] | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo and timezone_name:
            parsed = parsed.astimezone(ZoneInfo(timezone_name))
        return parsed.hour, parsed.minute
    except (TypeError, ValueError, KeyError):
        return None


def _deduplicate(items: list[dict]) -> list[dict]:
    unique: dict[str, dict] = {}
    for item in items:
        key = str(item.get("medication_id") or item.get("prescription_item_id") or item.get("id") or item.get("medication_name") or item.get("display_name"))
        unique.setdefault(key, item)
    return list(unique.values())


async def resolve_prescribed_drug(state: dict) -> ResolutionResult:
    analysis = state.get("intent_analysis") or {}
    ref_type = str(analysis.get("reference_type") or "none")
    patient_id = state.get("patient_id")
    client_date = state.get("client_date")
    if not patient_id:
        return ResolutionResult(ResolutionStatus.BACKEND_UNAVAILABLE, reference_type=ref_type)

    schedule: dict | None = None
    current: dict | None = None
    try:
        if ref_type in {"schedule_time", "dose_period", "next_dose", "recent_dose", "meal_relation"}:
            schedule = await get(
                f"/patients/{patient_id}/schedules",
                params={"date": client_date} if client_date else None,
            )
        if ref_type in {"drug_name", "prescription_ordinal", "current_medications"}:
            current = await get(
                "/patients/me/medications/current",
                params={"as_of": client_date} if client_date else None,
            )
    except BackendAPIError:
        return ResolutionResult(ResolutionStatus.BACKEND_UNAVAILABLE, reference_type=ref_type)

    matches: list[dict] = []
    value: str | None = None
    doses = list((schedule or {}).get("doses") or [])
    meds = list((current or {}).get("medications") or [])

    if ref_type == "schedule_time":
        value = analysis.get("schedule_time")
        try:
            hour, minute = (int(part) for part in str(value).split(":", 1))
        except (TypeError, ValueError):
            return ResolutionResult(ResolutionStatus.INSUFFICIENT_REFERENCE, reference_type=ref_type)
        timezone_name = (schedule or {}).get("timezone")
        matches = [d for d in doses if _local_time(d.get("current_scheduled_at"), timezone_name) == (hour, minute)]
    elif ref_type == "dose_period":
        value = str(analysis.get("dose_period") or "").casefold()
        slot = _PERIOD_TO_SLOT.get(value, value.upper())
        matches = [d for d in doses if str(d.get("dose_slot") or "").upper() == slot]
    elif ref_type == "next_dose":
        matches = [d for d in doses if str(d.get("status") or "PENDING").upper() not in {"TAKEN", "SKIPPED", "MISSED"}]
        matches.sort(key=lambda d: str(d.get("current_scheduled_at") or ""))
        matches = matches[:1]
    elif ref_type == "recent_dose":
        matches = [d for d in doses if str(d.get("status") or "").upper() in {"TAKEN", "MISSED"}]
        matches.sort(key=lambda d: str(d.get("current_scheduled_at") or ""), reverse=True)
        matches = matches[:1]
    elif ref_type == "meal_relation":
        value = str(analysis.get("meal_relation") or "").upper()
        matches = [d for d in doses if str(d.get("meal_relation") or "").upper() == value]
    elif ref_type == "prescription_ordinal":
        try:
            ordinal = int(analysis.get("prescription_ordinal"))
        except (TypeError, ValueError):
            return ResolutionResult(ResolutionStatus.INSUFFICIENT_REFERENCE, reference_type=ref_type)
        matches = meds[ordinal - 1:ordinal] if ordinal > 0 else []
        value = str(ordinal)
    elif ref_type == "drug_name":
        value = str(analysis.get("drug_name") or "").strip()
        if not value:
            return ResolutionResult(ResolutionStatus.INSUFFICIENT_REFERENCE, reference_type=ref_type)
        needle = value.casefold()
        matches = [m for m in meds if needle in str(m.get("display_name") or "").casefold()]
    elif ref_type == "recent_context":
        remembered = (state.get("memory_context") or {}).get("current_medication")
        if not isinstance(remembered, dict) or not remembered.get("display_name"):
            return ResolutionResult(ResolutionStatus.CONTEXT_EXPIRED, reference_type=ref_type)
        matches = [remembered]
    elif ref_type == "current_medications":
        matches = meds
    else:
        return ResolutionResult(ResolutionStatus.INSUFFICIENT_REFERENCE, reference_type=ref_type)

    matches = _deduplicate(matches)
    if not matches:
        if current is not None and not meds:
            status = ResolutionStatus.INACTIVE_PRESCRIPTION
        else:
            status = ResolutionStatus.NOT_FOUND
        return ResolutionResult(status, reference_type=ref_type, reference_value=value, schedule=schedule)
    status = ResolutionStatus.RESOLVED_ONE if len(matches) == 1 else ResolutionStatus.RESOLVED_MULTIPLE
    return ResolutionResult(status, matches, ref_type, value, schedule)
