from __future__ import annotations

from typing import cast

from langchain_core.runnables import RunnableConfig

from src.agents.planning_state import PlanningState
from src.common.exceptions import NotFoundException
from src.modules.agents.planner import PlanningNeedsReviewError
from src.modules.agents.repository import ScheduledDoseRepository


async def planning_input_gate_node(state: PlanningState, config: RunnableConfig) -> dict:
    """Read the patient context and APPROVED items without taking row locks."""
    configurable = config.get("configurable", {})
    dose_repo = cast(ScheduledDoseRepository, configurable["dose_repo"])

    patient_timezone, routine = await dose_repo.get_patient_context_unscoped(state["patient_id"])
    if patient_timezone is None:
        raise NotFoundException(message="Patient not found")

    item_pairs = await dose_repo.get_approved_items(state["patient_id"])
    if not item_pairs:
        raise PlanningNeedsReviewError("No approved prescription items are available for scheduling")

    return {
        "patient_timezone": patient_timezone,
        "routine": routine,
        "approved_item_pairs": item_pairs,
    }
