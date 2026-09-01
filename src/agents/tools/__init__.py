"""Agent tools. See cong_viec.md §2 for the full spec this follows.

Deliberately NOT implemented as LLM-callable tools (cong_viec.md §2.3):
  - Any write/edit on prescriptions or prescription_items: HITL constraint
    (cong_viec.md §4.4) — enforced by the DB credential being read-only on
    those tables, not by anything in this package.
  - Direct SMS/Zalo send: must go through trigger_red_alert -> backend, so
    the backend can rate-limit and audit.
  - Updating agent_runs metadata: SchedulingService.execute_run already writes
    the run's status/latency/dose count from inside the worker that produced
    them. api-contract.md exposes only GET /agent-runs/{id}, and an outside
    writer would race the worker for the same row.

Note: `record_dose_action` is added per user request, despite original
plan constraints regarding prompt injection risks.
"""

from src.agents.tools.drug_info_tools import search_drug_info
from src.agents.tools.drug_rag_tools import search_drug_formulary
from src.agents.tools.patient_tools import get_scheduled_doses

# Chỉ các capability tra cứu được phép dùng bởi chatbot.
READ_ONLY_TOOLS = [search_drug_formulary, search_drug_info, get_scheduled_doses]
ALL_TOOLS = READ_ONLY_TOOLS

# Generic conversation LLM gets no backend capability. Read operations route
# through deterministic intent nodes; write tools are invoked only by dedicated
# workflows after authorization/confirmation. Hiding schemas is the first
# least-privilege boundary, not merely a prompt instruction.
CHAT_TOOLS = []

__all__ = [
    "get_scheduled_doses",
    "search_drug_info",
    "search_drug_formulary",
    "READ_ONLY_TOOLS",
    "ALL_TOOLS",
    "CHAT_TOOLS",
]
