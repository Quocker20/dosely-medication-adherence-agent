from __future__ import annotations

from typing import cast

from langchain_core.runnables import RunnableConfig

from src.agents.planning_state import PlanningState
from src.core.config import Settings
from src.modules.agents.grouping import schedule_rows_hmac
from src.modules.agents.planner import expand_schedule


async def planning_generate_candidate_node(state: PlanningState, config: RunnableConfig) -> dict:
    """Build the deterministic draft — pure rule, no LLM grouping.

    Notification grouping đã bỏ (quyết định pure-rule): mỗi cữ thông báo riêng.
    Giữ nguyên expand_schedule code-validated; không gọi LLM, không candidate_view.
    """
    settings = cast(Settings, config.get("configurable", {})["settings"])
    rows = expand_schedule(
        state["plannable_items"],
        state["routine_times"],
        state["patient_timezone"],
        today=state["today_local"],
        horizon_days=settings.schedule_horizon_days,
        default_min_gap_minutes=settings.min_dose_gap_minutes,
        max_treatment_days=settings.max_treatment_days,
    )
    rows = [row for row in rows if row.current_scheduled_at > state["run_now"]]
    draft_hash = schedule_rows_hmac(
        rows,
        settings.jwt_secret_key,
        include_notification_groups=False,
    )

    return {
        "naive_rows_draft": rows,
        "draft_view_hash": draft_hash,
        "grouping_proposal": None,
        "llm_attempted": False,
        "llm_model_version": None,
        "llm_prompt_version": None,
        "llm_latency_ms": None,
        "llm_error": None,
        "candidate_source": "deterministic",
    }
