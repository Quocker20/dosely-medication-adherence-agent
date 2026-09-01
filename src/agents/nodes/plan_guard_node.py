"""Post-LLM guardrail: validate semantic plans before any tool or data access."""
from __future__ import annotations

from langchain_core.messages import AIMessage

from src.agents.semantic_plan import SemanticPlan, SemanticStep
from src.agents.state import AgentState

_READ_TOOLS = {
    "get_schedule", "get_next_dose", "get_current_medications", "explain_current_medications",
    "resolve_medication", "resolve_prescribed_medication",
    "search_drug_knowledge", "search_drug_information", "search_medication_catalog",
}
_BLOCKED_REPLY = (
    "Mình không thể tự quyết định thay đổi liều, ngừng thuốc hoặc thay đổi điều trị. "
    "Bạn hãy giữ nguyên chỉ dẫn hiện tại và xác nhận với bác sĩ/dược sĩ."
)


_WRITE_TOOLS = {"report_meal_shift"}
_WRITE_TOOLS.add("record_adverse_event")


def _validate_step(plan: SemanticStep) -> list[str]:
    errors: list[str] = []
    if plan.requested_action == "change_treatment":
        errors.append("treatment_change_not_authorized")
    if plan.tool == "report_meal_shift" and plan.requested_action not in {"change_schedule", "read", "other"}:
        errors.append("invalid_schedule_action")
    if plan.tool in {"search_drug_knowledge", "search_drug_information", "search_medication_catalog"} and not plan.drug_name and not plan.needs_clarification:
        errors.append("missing_drug_name")
    if plan.tool in {"resolve_medication", "resolve_prescribed_medication"} and plan.drug_reference_type == "none":
        errors.append("missing_prescription_reference")
    if plan.tool == "record_adverse_event" and not plan.symptoms:
        errors.append("missing_symptoms")
    if plan.tool in _READ_TOOLS and plan.requested_action in {"change_schedule", "change_treatment"}:
        errors.append("write_action_on_read_tool")
    return errors


def validate_plan(plan: SemanticPlan) -> list[str]:
    errors: list[str] = []
    if len(plan.steps) > 3:
        errors.append("too_many_steps")
    if sum(step.tool in _WRITE_TOOLS for step in plan.steps) > 1:
        errors.append("multiple_write_steps")
    if len(plan.steps) > 1 and any(step.tool in {"clarify", "general_response"} for step in plan.steps):
        errors.append("non_composable_step")
    signatures = [
        (step.tool, step.date_reference, step.schedule_time, step.drug_name, tuple(step.topics))
        for step in plan.steps
    ]
    if len(signatures) != len(set(signatures)):
        errors.append("duplicate_steps")
    for index, step in enumerate(plan.steps, start=1):
        errors.extend(f"step_{index}:{error}" for error in _validate_step(step))
    return errors


async def plan_guard_node(state: AgentState) -> dict:
    raw = state.get("semantic_plan") or {}
    try:
        plan = SemanticPlan.model_validate(raw)
    except Exception:
        return {"semantic_plan_valid": False, "use_legacy_classifier": True, "plan_errors": ["invalid_schema"]}
    errors = validate_plan(plan)
    if errors:
        unsafe = any(
            error.endswith(":treatment_change_not_authorized")
            or error.endswith(":write_action_on_read_tool")
            or error == "multiple_write_steps"
            for error in errors
        )
        if not unsafe:
            return {
                "semantic_plan_valid": False,
                "use_legacy_classifier": True,
                "plan_errors": errors,
            }
        return {
            # Internal fail-safe only; output_guard replaces it with an LLM
            # response based on the question and one refusal reason.
            "messages": [AIMessage(content=_BLOCKED_REPLY)],
            "semantic_plan_valid": False,
            "safety_blocked": True,
            "safety_reason": errors[0],
            "refusal_reason": errors[0],
            "plan_errors": errors,
        }
    return {"semantic_plan_valid": True, "plan_errors": []}
