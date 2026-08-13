"""Agent tools. See cong_viec.md §2 for the full spec this follows.

Deliberately NOT implemented as LLM-callable tools (cong_viec.md §2.3):
  - Any write/edit on prescriptions or prescription_items: HITL constraint
    (cong_viec.md §4.4) — enforced by the DB credential being read-only on
    those tables, not by anything in this package.
  - Direct SMS/Zalo send: must go through trigger_red_alert -> backend, so
    the backend can rate-limit and audit.

Note: `record_dose_action` is added per user request, despite original
plan constraints regarding prompt injection risks.
"""
from src.agents.tools.agent_run_tools import update_agent_run
from src.agents.tools.drug_info_tools import search_drug_info
from src.agents.tools.example_tool import search_knowledge
from src.agents.tools.health_tools import record_health_survey
from src.agents.tools.patient_tools import (
    get_adherence_stats,
    get_patient_profile,
    get_prescriptions,
    get_scheduled_doses,
)
from src.agents.tools.safety_tools import trigger_red_alert
from src.agents.tools.schedule_tools import record_dose_action, reschedule_remaining_doses

READ_ONLY_TOOLS = [
    get_prescriptions,
    get_patient_profile,
    get_scheduled_doses,
    get_adherence_stats,
    search_drug_info,
]

WRITE_TOOLS = [
    reschedule_remaining_doses,
    record_health_survey,
    trigger_red_alert,
    update_agent_run,
    record_dose_action,
]

ALL_TOOLS = READ_ONLY_TOOLS + WRITE_TOOLS

# Tool set cho patient-facing chat agent. Loại update_agent_run: đó là
# metadata cho job chạy nền (Planning Agent), không phải thứ bệnh nhân
# trò chuyện sẽ cần — không có lý do gì để đưa nó vào tay LLM hội thoại.
CHAT_TOOLS = READ_ONLY_TOOLS + [
    reschedule_remaining_doses,
    record_health_survey,
    trigger_red_alert,
    record_dose_action,
]

__all__ = [
    "get_prescriptions",
    "get_patient_profile",
    "get_scheduled_doses",
    "get_adherence_stats",
    "search_drug_info",
    "reschedule_remaining_doses",
    "record_health_survey",
    "trigger_red_alert",
    "update_agent_run",
    "record_dose_action",
    "search_knowledge",
    "READ_ONLY_TOOLS",
    "WRITE_TOOLS",
    "ALL_TOOLS",
    "CHAT_TOOLS",
]
