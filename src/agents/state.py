from __future__ import annotations

from typing import Annotated, Any, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class AgentState(TypedDict, total=False):
    """State schema cho LangGraph agent.

    Mỗi node đọc và ghi vào state này.
    total=False cho phép tất cả fields là optional.
    """

    messages: Annotated[list[BaseMessage], add_messages]
    # De-identified theo cong_viec.md §4.5: truyền patient_id, không truyền
    # họ tên/SĐT/địa chỉ vào state hay prompt.
    patient_id: str
    # True khi safety_guard_node đã escalate (Red Alert) ở turn này — graph
    # dùng field này để ngắt, không đi tiếp vào agent_node bình thường.
    escalated: bool
    # Nhãn do classify_intent_node gán — graph dùng để route sang
    # rescheduling_node hay agent_node bình thường. Cũng dùng cho audit log.
    intent: str
    error: str
    metadata: dict


class PlanningState(TypedDict, total=False):
    """State cho Planning Agent (FR-2.1).

    Agent chỉ được sinh `candidates[*]["times"]`. Mọi trường lâm sàng đi kèm
    (liều, số cữ, số ngày) là bản sao read-only của đơn đã duyệt và sẽ bị
    validator đối chiếu lại ở `validate_candidate_node`.
    """

    prescription: Any  # modules.planning.core.clinical.Prescription
    routine: Any  # modules.planning.core.clinical.PatientRoutine
    anchors: dict[str, str]
    candidates: list[dict[str, Any]]
    review_notes: list[str]
    slots: list[Any]  # modules.planning.core.clinical.ScheduleSlot
    error: str
