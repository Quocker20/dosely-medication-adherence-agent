from __future__ import annotations

from typing import Annotated, TypedDict

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
    # Deterministic vocative loaded once from /patients/me/profile for this turn.
    # It contains no name or other profile PII.
    patient_address: str
    client_date: str
    client_datetime: str
    # True khi safety_guard_node đã escalate (Red Alert) ở turn này — graph
    # dùng field này để ngắt, không đi tiếp vào agent_node bình thường.
    escalated: bool
    # Deterministic medication-policy gate. When true, graph ends before any
    # intent classifier, chat model, tool, or retrieval call.
    safety_blocked: bool
    safety_reason: str
    scope_blocked: bool
    scope_category: str
    output_guarded: bool
    output_errors: list[str]
    # Nhãn do classify_intent_node gán — graph dùng để route sang
    # rescheduling_node hay agent_node bình thường. Cũng dùng cho audit log.
    intent: str
    intent_analysis: dict
    # Result of SafeDrugRAG's citation and factual-grounding validation.
    grounding_valid: bool
    grounding_errors: list[str]
    error: str
    metadata: dict
    memory_context: dict
