from __future__ import annotations

from typing import cast

from langchain_core.runnables import RunnableConfig

from src.agents.planning_state import PlanningState
from src.modules.agents.repository import ScheduledDoseRepository


async def planning_persist_node(state: PlanningState, config: RunnableConfig) -> dict:
    """Persist only the deterministically rebuilt candidate schedule."""
    dose_repo = cast(
        ScheduledDoseRepository,
        config.get("configurable", {})["dose_repo"],
    )
    if state["is_reschedule"]:
        await dose_repo.delete_future_pending(state["patient_id"], now=state["commit_now"])

    row_dicts = [
        {
            "prescription_item_id": row.prescription_item_id,
            "medication_id": row.medication_id,
            "dose_slot": row.dose_slot,
            "dose_value": row.dose_value,
            "dose_unit": row.dose_unit,
            "meal_relation": row.meal_relation,
            "patient_id": state["patient_id"],
            "original_scheduled_at": row.original_scheduled_at,
            "current_scheduled_at": row.current_scheduled_at,
            "status": row.status,
            "snooze_count": row.snooze_count,
            "notification_group_id": row.notification_group_id,
            "is_critical": row.is_critical,
        }
        for row in state["candidate_rows"]
    ]
    inserted_count = await dose_repo.bulk_insert_doses(row_dicts)
    return {"generated_dose_count": inserted_count}
