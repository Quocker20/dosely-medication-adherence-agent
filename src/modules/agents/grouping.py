"""Deterministic notification grouping for already-validated dose rows.

The LLM may only propose groups of row indexes. This module is the code
gate that decides whether those groups are structurally safe to persist.
It never changes a medication, dose, slot, or scheduled timestamp.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field

from src.modules.agents.planner import ScheduleRow


class DoseGroupingProposal(BaseModel):
    """LLM output: clusters of row indexes sharing one notification."""

    groups: list[list[int]] = Field(default_factory=list)


class GroupingRejectedError(ValueError):
    """A proposal cannot be applied without violating grouping rules."""


def candidate_view_for_llm(rows: list[ScheduleRow], patient_timezone: str) -> list[dict[str, Any]]:
    """Return the minimal, non-clinical view the grouping LLM is allowed."""
    timezone = ZoneInfo(patient_timezone)
    return [
        {
            "index": index,
            "dose_slot": row.dose_slot,
            "local_time": row.current_scheduled_at.astimezone(timezone).isoformat(),
            "meal_relation": row.meal_relation,
        }
        for index, row in enumerate(rows)
    ]


def schedule_rows_hmac(
    rows: list[ScheduleRow],
    secret: str,
    *,
    include_notification_groups: bool,
) -> str:
    """HMAC a canonical schedule projection without storing plaintext data."""
    payload = [
        {
            "prescription_item_id": str(row.prescription_item_id),
            "medication_id": str(row.medication_id) if row.medication_id else None,
            "dose_slot": row.dose_slot,
            "dose_value": _decimal_string(row.dose_value),
            "dose_unit": row.dose_unit,
            "meal_relation": row.meal_relation,
            "original_scheduled_at": row.original_scheduled_at.isoformat(),
            "current_scheduled_at": row.current_scheduled_at.isoformat(),
            "notification_group_id": (
                str(row.notification_group_id) if include_notification_groups and row.notification_group_id else None
            ),
        }
        for row in rows
    ]
    canonical = json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode()
    return hmac.new(secret.encode(), canonical, hashlib.sha256).hexdigest()


def apply_dose_grouping(
    naive_rows: list[ScheduleRow],
    proposal: DoseGroupingProposal,
    window_minutes: int,
    patient_timezone: str,
) -> list[ScheduleRow]:
    """Assign notification group IDs without changing dose schedule fields."""
    if window_minutes < 0:
        raise GroupingRejectedError("Notification grouping window cannot be negative")

    timezone = ZoneInfo(patient_timezone)
    result = list(naive_rows)
    seen_indexes: set[int] = set()

    for group in proposal.groups:
        if len(group) < 2:
            raise GroupingRejectedError("A notification group must contain at least two doses")
        if len(set(group)) != len(group):
            raise GroupingRejectedError("A notification group contains a duplicate index")
        if any(index < 0 or index >= len(naive_rows) for index in group):
            raise GroupingRejectedError("A notification group contains an out-of-range index")
        if seen_indexes.intersection(group):
            raise GroupingRejectedError("A dose index appears in more than one notification group")

        rows = [naive_rows[index] for index in group]
        item_ids = {row.prescription_item_id for row in rows}
        if len(item_ids) != len(rows):
            raise GroupingRejectedError("Two doses from the same prescription item cannot share a group")

        clinical_days = {row.current_scheduled_at.astimezone(timezone).date() for row in rows}
        if len(clinical_days) != 1:
            raise GroupingRejectedError("A notification group cannot cross a patient's local day")

        timestamps = [row.current_scheduled_at for row in rows]
        if len(set(timestamps)) != 1:
            raise GroupingRejectedError("A notification group must contain doses due at the exact same time")
        if len({row.meal_relation for row in rows}) != 1:
            raise GroupingRejectedError("A notification group must use one compatible meal instruction")
        if max(timestamps) - min(timestamps) > timedelta(minutes=window_minutes):
            raise GroupingRejectedError("A notification group exceeds the configured reminder window")

        group_id = uuid.uuid4()
        for index in group:
            original = naive_rows[index]
            grouped = replace(original, notification_group_id=group_id)
            _assert_schedule_unchanged(original, grouped)
            result[index] = grouped
        seen_indexes.update(group)

    return result


def _assert_schedule_unchanged(original: ScheduleRow, grouped: ScheduleRow) -> None:
    """Make the notification-only invariant executable, not documentary."""
    before = replace(original, notification_group_id=None)
    after = replace(grouped, notification_group_id=None)
    if before != after:
        raise AssertionError("Notification grouping changed a clinical schedule field")


def _decimal_string(value: Decimal) -> str:
    return format(value, "f")
