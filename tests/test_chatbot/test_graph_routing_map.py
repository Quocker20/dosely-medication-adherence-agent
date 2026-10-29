"""Characterisation of the plan_guard conditional-edge map (ruff F601).

The path map handed to ``add_conditional_edges("plan_guard", ...)`` repeated the
``"clarification"`` and ``"clarify"`` keys; Python silently keeps the last
value, so the duplicates were harmless but hid whether a route had been
dropped. This pins which nodes plan_guard can reach and that every route string
the router functions can return is actually a key of that map.
"""

import pytest

from src.chatbot import graph as graph_module

EXPECTED_PLAN_GUARD_TARGETS = {
    "output_guard",
    "clarification",
    "rescheduling",
    "drug_rag",
    "medication_catalog",
    "adverse_event",
    "recent_adverse_event",
    "scheduled_drug_info",
    "prescribed_drug_info",
    "current_medications",
    "explain_my_medications",
    "next_dose",
    "today_schedule",
    "agent",
    "multi_tool_executor",
}

INTENTS = [
    "multi_tool",
    "report_meal_shift",
    "report_adverse_event",
    "get_recent_adverse_event",
    "ask_drug_catalog",
    "ask_drug_info",
    "ask_scheduled_drug_info",
    "ask_prescribed_drug_info",
    "ask_my_medications",
    "explain_my_medications",
    "ask_next_dose",
    "ask_schedule",
    "clarify",
    "something_else",
]


@pytest.fixture(scope="module")
def plan_guard_targets():
    drawable = graph_module.build_graph().get_graph()
    return {edge.target for edge in drawable.edges if edge.source == "plan_guard"}


def test_plan_guard_reaches_exactly_the_expected_nodes(plan_guard_targets):
    assert plan_guard_targets == EXPECTED_PLAN_GUARD_TARGETS


@pytest.mark.parametrize("intent", INTENTS)
def test_every_route_plan_guard_can_return_has_an_edge(intent, plan_guard_targets):
    state = {"safety_blocked": False, "semantic_plan_valid": True, "intent": intent}
    assert graph_module._route_after_plan_guard(state) in plan_guard_targets


def test_clarify_intent_goes_to_the_clarification_node():
    state = {"safety_blocked": False, "semantic_plan_valid": True, "intent": "clarify"}
    assert graph_module._route_after_plan_guard(state) == "clarification"
