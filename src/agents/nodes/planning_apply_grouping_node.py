from __future__ import annotations

from langchain_core.runnables import RunnableConfig

from src.agents.planning_state import PlanningState


async def planning_apply_grouping_node(state: PlanningState, config: RunnableConfig) -> dict:
    """Pure-rule: không gom nhóm — mỗi cữ một thông báo riêng.

    Đã bỏ LLM grouping theo quyết định pure-rule. Giữ node để không phá graph
    wiring, nhưng luôn pass-through naive_rows_fresh.
    """
    return {"candidate_rows": state["naive_rows_fresh"]}
