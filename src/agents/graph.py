from langgraph.graph import END, StateGraph
from langgraph.prebuilt import ToolNode

from src.agents.nodes.chat_node import agent_node, should_continue
from src.agents.state import AgentState
from src.agents.tools import CHAT_TOOLS


def build_graph() -> StateGraph:
    graph = StateGraph(AgentState)

    graph.add_node("agent", agent_node)
    graph.add_node("tools", ToolNode(CHAT_TOOLS, handle_tool_errors=True))

    graph.set_entry_point("agent")
    # ReAct loop: agent decides to call a tool -> tools runs -> back to agent,
    # until agent replies with no tool_calls left.
    graph.add_conditional_edges("agent", should_continue, {"tools": "tools", "end": END})
    graph.add_edge("tools", "agent")

    return graph.compile()


agent = build_graph()
