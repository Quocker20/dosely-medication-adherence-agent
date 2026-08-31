from __future__ import annotations

import uuid
from datetime import datetime
from typing import cast
from zoneinfo import ZoneInfo

from langchain_core.runnables import RunnableConfig

from src.agents.planning_state import PlanningState
from src.core.config import Settings
from src.modules.agents.planner import (
    PlannableItem,
    RoutineTimes,
    validate_frequency_guardrails,
)
from src.modules.patients.models import PatientRoutine
from src.modules.prescriptions.models import PrescriptionItem


async def planning_normalize_node(state: PlanningState, config: RunnableConfig) -> dict:
    """Convert ORM inputs into immutable planning snapshots."""
    settings = cast(Settings, config.get("configurable", {})["settings"])
    return normalize_planning_inputs(
        state["approved_item_pairs"],
        state.get("routine"),
        state["patient_timezone"],
        state["run_now"],
        settings.max_frequency_per_day,
    )


def normalize_planning_inputs(
    item_pairs: list[tuple[PrescriptionItem, uuid.UUID]],
    routine: PatientRoutine | None,
    patient_timezone: str,
    run_now: datetime,
    max_frequency_per_day: int,
) -> dict:
    """Pure projection shared by the draft and locked revalidation phases."""
    plannable_items = [
        PlannableItem(
            id=item.id,
            medication_id=item.medication_id,
            dose_unit=item.dose_unit,
            morning_dose=item.morning_dose,
            noon_dose=item.noon_dose,
            evening_dose=item.evening_dose,
            bedtime_dose=item.bedtime_dose,
            meal_relation=item.meal_relation,
            minimum_interval_minutes=item.minimum_interval_minutes,
            start_date=item.start_date,
            end_date=item.end_date,
            is_critical=item.is_critical,
            interval_days=getattr(item, "interval_days", 1) or 1,
        )
        for item, _prescription_id in item_pairs
    ]
    validate_frequency_guardrails(plannable_items, max_frequency_per_day)
    routine_times = RoutineTimes(
        wake=routine.wake_time if routine else None,
        breakfast=routine.breakfast_time if routine else None,
        lunch=routine.lunch_time if routine else None,
        dinner=routine.dinner_time if routine else None,
        sleep=routine.sleep_time if routine else None,
    )
    return {
        "plannable_items": plannable_items,
        "routine_times": routine_times,
        "today_local": run_now.astimezone(ZoneInfo(patient_timezone)).date(),
    }
