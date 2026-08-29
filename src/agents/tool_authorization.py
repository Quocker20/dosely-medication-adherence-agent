"""Non-LLM authorization boundary for agent tool execution."""
from __future__ import annotations

from src.core.security import decode_token, get_actor_token


class ToolAuthorizationError(PermissionError):
    pass


WRITE_TOOL_INTENTS = {
    "reschedule_remaining_doses": {"report_meal_shift"},
    "record_dose_action": {"report_dose_action"},
    "record_health_survey": {"report_health_survey"},
    "trigger_red_alert": {"emergency"},
}


def authorize_patient_write(tool_name: str, patient_id: str, *, intent: str) -> None:
    """Fail closed unless the request JWT owns the patient and intent permits the write."""
    if intent not in WRITE_TOOL_INTENTS.get(tool_name, set()):
        raise ToolAuthorizationError(f"Tool {tool_name} is not allowed for intent {intent}")
    token = get_actor_token()
    if not token:
        raise ToolAuthorizationError("Patient write requires an actor token")
    payload = decode_token(token)
    if payload.get("type") != "access" or payload.get("role") != "PATIENT":
        raise ToolAuthorizationError("Patient write requires a patient access token")
    if str(payload.get("sub")) != str(patient_id):
        raise ToolAuthorizationError("Patient ownership mismatch")
