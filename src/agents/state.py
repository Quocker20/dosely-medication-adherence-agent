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
    error: str
    metadata: dict
