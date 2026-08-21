from __future__ import annotations

from typing import cast

from langchain_core.runnables import RunnableConfig

from src.agents.planning_state import PlanningState
from src.core.config import Settings
from src.modules.agents.grouping import GroupingRejectedError, apply_dose_grouping


async def planning_apply_grouping_node(state: PlanningState, config: RunnableConfig) -> dict:
    """Apply a matching LLM proposal through deterministic structural rules."""
    if not state.get("grouping_eligible"):
        return {"candidate_rows": state["naive_rows_fresh"]}

    settings = cast(Settings, config.get("configurable", {})["settings"])
    proposal = state.get("grouping_proposal")
    if proposal is None:
        return {"candidate_rows": state["naive_rows_fresh"]}
    if not proposal.groups:
        return {
            "candidate_rows": state["naive_rows_fresh"],
            "candidate_source": "deterministic",
        }

    try:
        grouped_rows = apply_dose_grouping(
            state["naive_rows_fresh"],
            proposal,
            settings.notification_group_window_minutes,
            state["patient_timezone"],
        )
    except GroupingRejectedError:
        return {
            "candidate_rows": state["naive_rows_fresh"],
            "candidate_source": "deterministic_fallback_invalid_proposal",
        }
    return {"candidate_rows": grouped_rows, "candidate_source": "llm_grouped"}
