"""Agent tools. See cong_viec.md §2 for the full spec this follows.

Deliberately NOT implemented as LLM-callable tools (cong_viec.md §2.3):
  - record_dose_action: must go straight from the notification button to
    the API, bypassing the agent entirely. If the LLM could call this, a
    prompt injection (via OCR text or survey free-text) could mark a missed
    dose as "taken" and silently defeat the Red Alert missed-dose trigger.
  - Any write/edit on prescriptions or prescription_items: HITL constraint
    (cong_viec.md §4.4) — enforced by the DB credential being read-only on
    those tables, not by anything in this package.
  - Direct SMS/Zalo send: must go through trigger_red_alert -> backend, so
    the backend can rate-limit and audit.
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
from src.agents.tools.schedule_tools import reschedule_remaining_doses

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
]

ALL_TOOLS = READ_ONLY_TOOLS + WRITE_TOOLS

# Tool set cho patient-facing chat agent. Loại update_agent_run: đó là
# metadata cho job chạy nền (Planning Agent), không phải thứ bệnh nhân
# trò chuyện sẽ cần — không có lý do gì để đưa nó vào tay LLM hội thoại.
CHAT_TOOLS = READ_ONLY_TOOLS + [
    reschedule_remaining_doses,
    record_health_survey,
    trigger_red_alert,
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
    "search_knowledge",
    "READ_ONLY_TOOLS",
    "WRITE_TOOLS",
    "ALL_TOOLS",
    "CHAT_TOOLS",
]
