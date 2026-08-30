"""Single-purpose executor: ask one focused clarification question."""
from langchain_core.messages import AIMessage

from src.agents.state import AgentState


async def clarification_node(state: AgentState) -> dict:
    plan = state.get("semantic_plan") or {}
    steps = plan.get("steps") or []
    step = steps[0] if steps else plan
    question = str(step.get("clarifying_question") or "").strip()
    if not question:
        drug = str(step.get("drug_name") or "thuốc này").strip()
        question = f"Bạn muốn biết công dụng, cách dùng, tác dụng phụ, chống chỉ định hay tương tác của {drug}?"
    return {"messages": [AIMessage(content=question)]}
