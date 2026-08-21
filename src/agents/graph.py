from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import ToolNode

# pyrefly: ignore [missing-import]
from src.agents.nodes.chat_node import agent_node, should_continue
from src.agents.nodes.classify_intent_node import classify_intent_node
from src.agents.nodes.rescheduling_node import rescheduling_node
from src.agents.nodes.safety_guard_node import safety_guard_node
from src.agents.state import AgentState
from src.agents.tools import CHAT_TOOLS


def _route_after_safety_guard(state: AgentState) -> str:
    return "end" if state.get("escalated") or state.get("safety_blocked") else "classify_intent"


def _route_after_classify_intent(state: AgentState) -> str:
    if state.get("intent") == "report_meal_shift":
        return "rescheduling"
    # TODO: route "ask_drug_info" -> drug_rag once src/rag_retrieval (branch RAG) is merged.
    return "agent"


def build_graph() -> CompiledStateGraph:
    graph = StateGraph(AgentState)

    graph.add_node("safety_guard", safety_guard_node)
    graph.add_node("classify_intent", classify_intent_node)
    graph.add_node("rescheduling", rescheduling_node)
    graph.add_node("agent", agent_node)
    graph.add_node("tools", ToolNode(CHAT_TOOLS, handle_tool_errors=True))

    # safety_guard chạy trên MỌI turn, TRƯỚC bất kỳ phân loại/chat nào (Kế
    # hoạch tầng 2 §1.3 + §6). Escalate -> dừng ngay với câu trả lời cố định.
    graph.set_entry_point("safety_guard")
    graph.add_conditional_edges(
        "safety_guard", _route_after_safety_guard, {"classify_intent": "classify_intent", "end": END}
    )

    # meal shift có route riêng, tách khỏi ReAct loop.
    graph.add_conditional_edges(
        "classify_intent",
        _route_after_classify_intent,
        {"rescheduling": "rescheduling", "agent": "agent"},
    )
    graph.add_edge("rescheduling", END)

    # ReAct loop: agent decides to call a tool -> tools runs -> back to agent,
    # until agent replies with no tool_calls left.
    # TODO: route "end" -> grounding_validator once src/rag_retrieval (branch RAG) is merged.
    graph.add_conditional_edges("agent", should_continue, {"tools": "tools", "end": END})
    graph.add_edge("tools", "agent")

    return graph.compile()


agent = build_graph()
