from __future__ import annotations

import asyncio
import json
import time
from typing import cast

from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig

from src.agents.planning_state import PlanningState
from src.core.config import Settings
from src.modules.agents.grouping import (
    DoseGroupingProposal,
    candidate_view_for_llm,
    schedule_rows_hmac,
)
from src.modules.agents.planner import expand_schedule
from src.modules.planning.core.llm import get_llm

_GROUPING_PROMPT_VERSION = "notification-grouping-v1"


async def planning_generate_candidate_node(state: PlanningState, config: RunnableConfig) -> dict:
    """Build the deterministic draft, then optionally ask LLM for index groups."""
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

    base_result = {
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
    if not settings.planning_grouping_enabled or state["is_reschedule"] or len(rows) < 2:
        return base_result

    view = candidate_view_for_llm(rows, state["patient_timezone"])
    prompt = HumanMessage(
        content=(
            "Group only the supplied row indexes into reminder clusters. "
            "Each group must contain at least two different indexes. Omit indexes "
            "that should remain separate. Do not invent indexes.\n"
            + json.dumps(view, ensure_ascii=True, separators=(",", ":"))
        )
    )
    started = time.perf_counter()
    try:
        llm = get_llm(temperature=0).with_structured_output(
            DoseGroupingProposal,
            include_raw=True,
        )
        response = await asyncio.wait_for(
            llm.ainvoke([prompt]),
            timeout=settings.planning_agent_timeout_ms / 1000,
        )
        actual_model = settings.model_name
        if isinstance(response, dict) and "parsed" in response:
            parsing_error = response.get("parsing_error")
            if parsing_error is not None:
                raise ValueError("Structured planning output could not be parsed")
            proposal = DoseGroupingProposal.model_validate(response["parsed"])
            raw = response.get("raw")
            metadata = getattr(raw, "response_metadata", {}) if raw is not None else {}
            actual_model = metadata.get("model_name") or metadata.get("model") or settings.model_name
        else:
            # Compatibility path for deterministic test doubles and providers
            # that return the parsed schema directly.
            proposal = DoseGroupingProposal.model_validate(response)
    except Exception as exc:
        return {
            **base_result,
            "llm_attempted": True,
            "llm_model_version": settings.model_name,
            "llm_prompt_version": _GROUPING_PROMPT_VERSION,
            "llm_latency_ms": int((time.perf_counter() - started) * 1000),
            "llm_error": type(exc).__name__[:100],
            "candidate_source": "deterministic_fallback_llm_error",
        }

    return {
        **base_result,
        "llm_attempted": True,
        "grouping_proposal": proposal,
        "llm_model_version": actual_model,
        "llm_prompt_version": _GROUPING_PROMPT_VERSION,
        "llm_latency_ms": int((time.perf_counter() - started) * 1000),
    }
