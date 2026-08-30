from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import ToolNode

# pyrefly: ignore [missing-import]
from src.agents.nodes.chat_node import agent_node, should_continue
from src.agents.nodes.classify_intent_node import classify_intent_node
from src.agents.nodes.clarification_node import clarification_node
from src.agents.nodes.current_medications_node import current_medications_node
from src.agents.nodes.drug_rag_node import drug_rag_node
from src.agents.nodes.explain_my_medications_node import explain_my_medications_node
from src.agents.nodes.next_dose_node import next_dose_node
from src.agents.nodes.multi_tool_executor_node import multi_tool_executor_node
from src.agents.nodes.output_guard_node import output_guard_node
from src.agents.nodes.plan_guard_node import plan_guard_node
from src.agents.nodes.prescribed_drug_info_node import prescribed_drug_info_node
from src.agents.nodes.rescheduling_node import rescheduling_node
from src.agents.nodes.safety_guard_node import safety_guard_node
from src.agents.nodes.scheduled_drug_info_node import scheduled_drug_info_node
from src.agents.nodes.scope_guard_node import scope_guard_node
from src.agents.nodes.semantic_planner_node import semantic_planner_node
from src.agents.nodes.today_schedule_node import today_schedule_node
from src.agents.nodes.adverse_event_node import adverse_event_node
from src.agents.nodes.recent_adverse_event_node import recent_adverse_event_node
from src.agents.state import AgentState
from src.agents.tools import CHAT_TOOLS


def _route_after_safety_guard(state: AgentState) -> str:
    return "output_guard" if state.get("escalated") or state.get("safety_blocked") else "scope_guard"


def _route_after_scope_guard(state: AgentState) -> str:
    return "output_guard" if state.get("scope_blocked") else "semantic_planner"


def _route_after_semantic_planner(state: AgentState) -> str:
    return "classify_intent" if state.get("use_legacy_classifier") else "plan_guard"


def _route_after_plan_guard(state: AgentState) -> str:
    if state.get("safety_blocked"):
        return "output_guard"
    if not state.get("semantic_plan_valid"):
        return "classify_intent"
    return _route_after_classify_intent(state)


def _route_after_classify_intent(state: AgentState) -> str:
    if state.get("intent") == "multi_tool":
        return "multi_tool_executor"
    if state.get("intent") == "report_meal_shift":
        return "rescheduling"
    if state.get("intent") == "report_adverse_event":
        return "adverse_event"
    if state.get("intent") == "get_recent_adverse_event":
        return "recent_adverse_event"
    if state.get("intent") == "ask_drug_info":
        return "drug_rag"
    if state.get("intent") == "ask_scheduled_drug_info":
        return "scheduled_drug_info"
    if state.get("intent") == "ask_prescribed_drug_info":
        return "prescribed_drug_info"
    if state.get("intent") == "ask_my_medications":
        return "current_medications"
    if state.get("intent") == "explain_my_medications":
        return "explain_my_medications"
    if state.get("intent") == "ask_next_dose":
        return "next_dose"
    if state.get("intent") == "ask_schedule":
        return "today_schedule"
    if state.get("intent") == "clarify":
        return "clarification"
    return "agent"


def build_graph() -> CompiledStateGraph:
    graph = StateGraph(AgentState)

    graph.add_node("safety_guard", safety_guard_node)
    graph.add_node("scope_guard", scope_guard_node)
    graph.add_node("output_guard", output_guard_node)
    graph.add_node("semantic_planner", semantic_planner_node)
    graph.add_node("plan_guard", plan_guard_node)
    graph.add_node("classify_intent", classify_intent_node)
    graph.add_node("rescheduling", rescheduling_node)
    graph.add_node("adverse_event", adverse_event_node)
    graph.add_node("recent_adverse_event", recent_adverse_event_node)
    graph.add_node("drug_rag", drug_rag_node)
    graph.add_node("scheduled_drug_info", scheduled_drug_info_node)
    graph.add_node("prescribed_drug_info", prescribed_drug_info_node)
    graph.add_node("current_medications", current_medications_node)
    graph.add_node("explain_my_medications", explain_my_medications_node)
    graph.add_node("next_dose", next_dose_node)
    graph.add_node("multi_tool_executor", multi_tool_executor_node)
    graph.add_node("today_schedule", today_schedule_node)
    graph.add_node("clarification", clarification_node)
    graph.add_node("agent", agent_node)
    graph.add_node("tools", ToolNode(CHAT_TOOLS, handle_tool_errors=True))

    # safety_guard chạy trên MỌI turn, TRƯỚC bất kỳ phân loại/chat nào (Kế
    # hoạch tầng 2 §1.3 + §6). Escalate -> dừng ngay với câu trả lời cố định.
    graph.set_entry_point("safety_guard")
    graph.add_conditional_edges(
        "safety_guard", _route_after_safety_guard, {"scope_guard": "scope_guard", "output_guard": "output_guard"}
    )
    graph.add_conditional_edges(
        "scope_guard", _route_after_scope_guard, {"semantic_planner": "semantic_planner", "output_guard": "output_guard"}
    )
    graph.add_conditional_edges(
        "semantic_planner", _route_after_semantic_planner,
        {"plan_guard": "plan_guard", "classify_intent": "classify_intent"},
    )
    graph.add_conditional_edges(
        "plan_guard", _route_after_plan_guard,
        {
            "output_guard": "output_guard", "classify_intent": "classify_intent",
            "rescheduling": "rescheduling", "drug_rag": "drug_rag",
            "adverse_event": "adverse_event",
            "recent_adverse_event": "recent_adverse_event",
            "scheduled_drug_info": "scheduled_drug_info", "prescribed_drug_info": "prescribed_drug_info",
            "current_medications": "current_medications", "explain_my_medications": "explain_my_medications",
            "next_dose": "next_dose", "today_schedule": "today_schedule",
            "clarification": "clarification", "agent": "agent",
            "multi_tool_executor": "multi_tool_executor",
        },
    )

    # meal shift có route riêng, tách khỏi ReAct loop.
    graph.add_conditional_edges(
        "classify_intent",
        _route_after_classify_intent,
        {
            "rescheduling": "rescheduling",
            "adverse_event": "adverse_event",
            "recent_adverse_event": "recent_adverse_event",
            "drug_rag": "drug_rag",
            "scheduled_drug_info": "scheduled_drug_info",
            "prescribed_drug_info": "prescribed_drug_info",
            "current_medications": "current_medications",
            "explain_my_medications": "explain_my_medications",
            "next_dose": "next_dose",
            "today_schedule": "today_schedule",
            "clarification": "clarification",
            "multi_tool_executor": "multi_tool_executor",
            "agent": "agent",
        },
    )
    graph.add_edge("rescheduling", "output_guard")
    graph.add_edge("adverse_event", "output_guard")
    graph.add_edge("recent_adverse_event", "output_guard")
    graph.add_edge("drug_rag", "output_guard")
    graph.add_edge("scheduled_drug_info", "output_guard")
    graph.add_edge("prescribed_drug_info", "output_guard")
    graph.add_edge("current_medications", "output_guard")
    graph.add_edge("explain_my_medications", "output_guard")
    graph.add_edge("next_dose", "output_guard")
    graph.add_edge("today_schedule", "output_guard")
    graph.add_edge("clarification", "output_guard")
    graph.add_edge("multi_tool_executor", "output_guard")
    graph.add_edge("output_guard", END)

    # ReAct loop: agent decides to call a tool -> tools runs -> back to agent,
    # until agent replies with no tool_calls left.
    graph.add_conditional_edges("agent", should_continue, {"tools": "tools", "end": "output_guard"})
    graph.add_edge("tools", "agent")

    return graph.compile()


agent = build_graph()
