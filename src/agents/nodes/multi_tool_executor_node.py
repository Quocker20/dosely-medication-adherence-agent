"""Execute an already-validated semantic plan of at most three steps."""
from __future__ import annotations

from copy import deepcopy

from langchain_core.messages import AIMessage

from src.agents.nodes.current_medications_node import current_medications_node
from src.agents.nodes.drug_rag_node import drug_rag_node
from src.agents.nodes.explain_my_medications_node import explain_my_medications_node
from src.agents.nodes.next_dose_node import next_dose_node
from src.agents.nodes.medication_catalog_node import medication_catalog_node
from src.agents.nodes.prescribed_drug_info_node import prescribed_drug_info_node
from src.agents.nodes.rescheduling_node import rescheduling_node
from src.agents.nodes.today_schedule_node import today_schedule_node
from src.agents.nodes.adverse_event_node import adverse_event_node
from src.agents.nodes.recent_adverse_event_node import recent_adverse_event_node
from src.agents.semantic_plan import SemanticPlan, SemanticStep, TOOL_TO_LEGACY_INTENT
from src.agents.state import AgentState

_EXECUTORS = {
    "get_schedule": today_schedule_node,
    "get_next_dose": next_dose_node,
    "resolve_medication": prescribed_drug_info_node,
    "search_drug_knowledge": drug_rag_node,
    "search_medication_catalog": medication_catalog_node,
}


def _analysis(step: SemanticStep) -> dict:
    return {
        "intent": TOOL_TO_LEGACY_INTENT[step.tool],
        "reference_type": step.drug_reference_type,
        "drug_name": step.drug_name,
        "symptoms": [item.model_dump() for item in step.symptoms],
        "schedule_time": step.schedule_time,
        "dose_period": step.dose_period,
        "statuses": step.statuses,
        "date_reference": step.date_reference,
        "topics": step.topics,
        "requested_action": step.requested_action,
        "needs_clarification": step.needs_clarification,
        "confidence": step.confidence,
        "parser": "semantic_multi_step",
    }


async def multi_tool_executor_node(state: AgentState) -> dict:
    plan = SemanticPlan.model_validate(state.get("semantic_plan") or {})
    sections: list[str] = []
    grounding_errors: list[str] = []
    metadata: dict = {}

    for index, step in enumerate(plan.steps, start=1):
        executor = _EXECUTORS.get(step.tool)
        if executor is None:
            sections.append(f"Kết quả {index}\nKhông thể thực hiện tác vụ này trong yêu cầu kết hợp.")
            continue
        step_state = deepcopy(dict(state))
        step_state["intent"] = TOOL_TO_LEGACY_INTENT[step.tool]
        step_state["intent_analysis"] = _analysis(step)
        result = await executor(step_state)  # type: ignore[arg-type]
        messages = result.get("messages") or []
        content = str(messages[-1].content) if messages else "Không có kết quả."
        # `purpose` is planner-internal text and may be in a different language.
        # Never expose it at the patient-facing boundary.
        sections.append(f"Kết quả {index}\n{content}")
        grounding_errors.extend(result.get("grounding_errors") or [])
        if result.get("metadata"):
            metadata[step.id] = result["metadata"]

    return {
        "messages": [AIMessage(content="\n\n".join(sections))],
        "grounding_valid": not grounding_errors,
        "grounding_errors": grounding_errors,
        "metadata": {"semantic_steps": metadata} if metadata else {},
    }
