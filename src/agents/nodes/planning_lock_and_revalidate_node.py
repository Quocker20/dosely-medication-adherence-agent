from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import cast

from langchain_core.runnables import RunnableConfig

from src.agents.nodes.planning_normalize_node import normalize_planning_inputs
from src.agents.planning_state import PlanningState
from src.common.exceptions import NotFoundException
from src.core.config import Settings
from src.modules.agents.grouping import schedule_rows_hmac
from src.modules.agents.planner import (
    PlanningNeedsReviewError,
    RetainedDoseSnapshot,
    expand_schedule,
    reconcile_reschedule_candidates,
)
from src.modules.agents.repository import ScheduledDoseRepository


async def planning_lock_and_revalidate_node(state: PlanningState, config: RunnableConfig) -> dict:
    """Re-read inputs under the commit transaction and rebuild the schedule."""
    configurable = config.get("configurable", {})
    dose_repo = cast(ScheduledDoseRepository, configurable["dose_repo"])
    settings = cast(Settings, configurable["settings"])
    clock = cast(Callable[[], datetime], configurable.get("clock", lambda: datetime.now(UTC)))
    commit_now = clock()

    patient_timezone, routine = await dose_repo.get_patient_context_unscoped(
        state["patient_id"],
        for_update=True,
    )
    if patient_timezone is None:
        raise NotFoundException(message="Patient not found")
    item_pairs = await dose_repo.get_approved_items(state["patient_id"], for_update=True)
    if not item_pairs:
        raise PlanningNeedsReviewError("No approved prescription items are available for scheduling")

    # Match the prescription-cancel lock order: clinical inputs first, dose
    # rows second. This avoids an inverse prescription<->dose lock cycle.
    locked_schedule = []
    if state["is_reschedule"]:
        locked_schedule = await dose_repo.lock_reschedule_window(
            state["patient_id"],
            now=commit_now,
        )

    normalized = normalize_planning_inputs(
        item_pairs,
        routine,
        patient_timezone,
        commit_now,
        settings.max_frequency_per_day,
    )
    overrides = await dose_repo.get_active_overrides(
        state["patient_id"],
        start=normalized["today_local"],
        end=normalized["today_local"] + timedelta(days=settings.schedule_horizon_days),
        for_update=True,
    )
    rows = expand_schedule(
        normalized["plannable_items"],
        normalized["routine_times"],
        patient_timezone,
        today=normalized["today_local"],
        horizon_days=settings.schedule_horizon_days,
        default_min_gap_minutes=settings.min_dose_gap_minutes,
        max_treatment_days=settings.max_treatment_days,
        overrides=overrides,
    )
    rows = [row for row in rows if row.current_scheduled_at > commit_now]

    if state["is_reschedule"]:
        rows = reconcile_reschedule_candidates(
            normalized["plannable_items"],
            rows,
            [
                RetainedDoseSnapshot(
                    prescription_item_id=dose.prescription_item_id,
                    dose_slot=dose.dose_slot,
                    original_scheduled_at=dose.original_scheduled_at,
                    current_scheduled_at=dose.current_scheduled_at,
                    status=dose.status,
                )
                for dose in locked_schedule
            ],
            now=commit_now,
            patient_timezone=patient_timezone,
            default_min_gap_minutes=settings.min_dose_gap_minutes,
        )

    commit_hash = schedule_rows_hmac(
        rows,
        settings.jwt_secret_key,
        include_notification_groups=False,
    )
    eligible = (
        not state["is_reschedule"]
        and state.get("grouping_proposal") is not None
        and commit_hash == state["draft_view_hash"]
    )
    source = state.get("candidate_source", "deterministic")
    if state["is_reschedule"]:
        source = "deterministic"
    elif commit_hash != state["draft_view_hash"] and state.get("llm_attempted"):
        source = "deterministic_fallback_stale_snapshot"

    return {
        **normalized,
        "patient_timezone": patient_timezone,
        "commit_now": commit_now,
        "routine": routine,
        "approved_item_pairs": item_pairs,
        "locked_schedule": locked_schedule,
        "naive_rows_fresh": rows,
        "commit_view_hash": commit_hash,
        "candidate_rows": rows,
        "candidate_source": source,
        "grouping_eligible": eligible,
    }
