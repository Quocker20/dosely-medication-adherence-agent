from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Literal, TypedDict

from src.modules.agents.grouping import DoseGroupingProposal
from src.modules.agents.models import ScheduledDose
from src.modules.agents.planner import PlannableItem, RoutineTimes, ScheduleRow
from src.modules.patients.models import PatientRoutine
from src.modules.prescriptions.models import PrescriptionItem

CandidateSource = Literal[
    "deterministic",
    "llm_grouped",
    "deterministic_fallback_llm_error",
    "deterministic_fallback_invalid_proposal",
    "deterministic_fallback_stale_snapshot",
]


class PlanningState(TypedDict, total=False):
    run_id: uuid.UUID
    patient_id: uuid.UUID
    is_reschedule: bool
    run_now: datetime
    commit_now: datetime

    patient_timezone: str
    routine: PatientRoutine | None
    approved_item_pairs: list[tuple[PrescriptionItem, uuid.UUID]]
    routine_times: RoutineTimes
    plannable_items: list[PlannableItem]
    today_local: date

    naive_rows_draft: list[ScheduleRow]
    draft_view_hash: str
    llm_attempted: bool
    grouping_proposal: DoseGroupingProposal | None
    llm_model_version: str | None
    llm_prompt_version: str | None
    llm_latency_ms: int | None
    llm_error: str | None

    locked_schedule: list[ScheduledDose]
    naive_rows_fresh: list[ScheduleRow]
    commit_view_hash: str
    candidate_rows: list[ScheduleRow]
    candidate_source: CandidateSource
    grouping_eligible: bool
    generated_dose_count: int

    run_status: Literal["COMPLETED"]
    input_hash: str
    output_hash: str
