from __future__ import annotations

from typing import Any, TypedDict


class AgentState(TypedDict, total=False):
    """State schema cho LangGraph agent.

    Mỗi node đọc và ghi vào state này.
    total=False cho phép tất cả fields là optional.
    """

    query: str
    context: str
    analysis: str
    response: str
    error: str
    metadata: dict


class PlanningState(TypedDict, total=False):
    """State cho Planning Agent (FR-2.1).

    Agent chỉ được sinh `candidates[*]["times"]`. Mọi trường lâm sàng đi kèm
    (liều, số cữ, số ngày) là bản sao read-only của đơn đã duyệt và sẽ bị
    validator đối chiếu lại ở `validate_candidate_node`.
    """

    prescription: Any  # models.clinical.Prescription
    routine: Any  # models.clinical.PatientRoutine
    anchors: dict[str, str]
    candidates: list[dict[str, Any]]
    review_notes: list[str]
    slots: list[Any]  # models.clinical.ScheduleSlot
    error: str
