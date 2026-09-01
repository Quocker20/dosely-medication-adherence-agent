"""Single-purpose executor: ask one focused clarification question."""
from langchain_core.messages import AIMessage

from src.agents.state import AgentState


async def clarification_node(state: AgentState) -> dict:
    plan = state.get("semantic_plan") or {}
    steps = plan.get("steps") or []
    step = steps[0] if steps else plan
    if step.get("requested_action") == "change_treatment":
        return {"messages": [AIMessage(content="Mình không hỗ trợ kê đơn, chọn kháng sinh hoặc tự thay đổi liều thuốc. Bạn hãy trao đổi trực tiếp với bác sĩ/dược sĩ để được tư vấn phù hợp, đặc biệt khi đang mang thai.")]}
    question = str(step.get("clarifying_question") or "").strip()
    if not question:
        drug = str(step.get("drug_name") or "thuốc này").strip()
        question = f"Bạn muốn biết công dụng, cách dùng, tác dụng phụ, chống chỉ định hay tương tác của {drug}?"
    return {"messages": [AIMessage(content=question)]}
