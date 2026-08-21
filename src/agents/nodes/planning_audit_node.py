from __future__ import annotations

from typing import cast

from langchain_core.runnables import RunnableConfig

from src.agents.planning_state import PlanningState
from src.core.config import Settings
from src.modules.agents.grouping import schedule_rows_hmac


async def planning_audit_node(state: PlanningState, config: RunnableConfig) -> dict:
    """Build structured, non-plaintext audit fingerprints for a successful run."""
    settings = cast(Settings, config.get("configurable", {})["settings"])
    return {
        "input_hash": schedule_rows_hmac(
            state["naive_rows_fresh"],
            settings.jwt_secret_key,
            include_notification_groups=False,
        ),
        "output_hash": schedule_rows_hmac(
            state["candidate_rows"],
            settings.jwt_secret_key,
            include_notification_groups=True,
        ),
        "run_status": "COMPLETED",
    }
