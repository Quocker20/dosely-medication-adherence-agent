from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph

from src.agents.nodes.planning_apply_grouping_node import planning_apply_grouping_node
from src.agents.nodes.planning_audit_node import planning_audit_node
from src.agents.nodes.planning_generate_candidate_node import planning_generate_candidate_node
from src.agents.nodes.planning_input_gate_node import planning_input_gate_node
from src.agents.nodes.planning_lock_and_revalidate_node import planning_lock_and_revalidate_node
from src.agents.nodes.planning_normalize_node import planning_normalize_node
from src.agents.nodes.planning_persist_node import planning_persist_node
from src.agents.planning_state import PlanningState


def _build_snapshot_graph() -> CompiledStateGraph:
    graph = StateGraph(PlanningState)
    graph.add_node("input_gate", planning_input_gate_node)
    graph.add_node("normalize", planning_normalize_node)
    graph.set_entry_point("input_gate")
    graph.add_edge("input_gate", "normalize")
    graph.add_edge("normalize", END)
    return graph.compile()


def _build_draft_graph() -> CompiledStateGraph:
    graph = StateGraph(PlanningState)
    graph.add_node("generate_candidate", planning_generate_candidate_node)
    graph.set_entry_point("generate_candidate")
    graph.add_edge("generate_candidate", END)
    return graph.compile()


def _build_commit_graph() -> CompiledStateGraph:
    graph = StateGraph(PlanningState)
    graph.add_node("deterministic_validate", planning_lock_and_revalidate_node)
    graph.add_node("apply_notification_grouping", planning_apply_grouping_node)
    graph.add_node("persist", planning_persist_node)
    graph.add_node("audit", planning_audit_node)
    graph.set_entry_point("deterministic_validate")
    graph.add_edge("deterministic_validate", "apply_notification_grouping")
    graph.add_edge("apply_notification_grouping", "persist")
    graph.add_edge("persist", "audit")
    graph.add_edge("audit", END)
    return graph.compile()


# Snapshot reads are committed before the draft graph performs network I/O.
planning_snapshot_graph = _build_snapshot_graph()
planning_draft_graph = _build_draft_graph()
planning_commit_graph = _build_commit_graph()
