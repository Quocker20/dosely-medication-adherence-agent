"""Graph cho Planning Agent — chỉ nối node, không chứa logic nghiệp vụ."""

from __future__ import annotations

import time
import uuid

from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph

from src.agents.nodes.planning_node import (
    build_slots_node,
    generate_candidate_node,
    input_gate_node,
    normalize_node,
    validate_candidate_node,
)
from src.agents.state import PlanningState
from src.models.clinical import (
    AgentRun,
    MedicationSchedule,
    PatientRoutine,
    Prescription,
    ScheduleStatus,
)


def _after_gate(state: PlanningState) -> str:
    return END if state.get("error") else "normalize"


def _after_validate(state: PlanningState) -> str:
    return END if state.get("error") else "build_slots"


def build_planning_graph() -> CompiledStateGraph:
    graph = StateGraph(PlanningState)

    graph.add_node("input_gate", input_gate_node)
    graph.add_node("normalize", normalize_node)
    graph.add_node("generate_candidate", generate_candidate_node)
    graph.add_node("validate_candidate", validate_candidate_node)
    graph.add_node("build_slots", build_slots_node)

    graph.set_entry_point("input_gate")
    graph.add_conditional_edges("input_gate", _after_gate)
    graph.add_edge("normalize", "generate_candidate")
    graph.add_edge("generate_candidate", "validate_candidate")
    graph.add_conditional_edges("validate_candidate", _after_validate)
    graph.add_edge("build_slots", END)

    return graph.compile()


planning_agent = build_planning_graph()


async def run_planning(
    prescription: Prescription,
    routine: PatientRoutine,
    schedule_id: str,
) -> MedicationSchedule:
    """Chạy agent và đóng gói kết quả thành MedicationSchedule.

    Trạng thái trả về:
    - FAILED khi input gate hoặc validator từ chối (không persist lịch nào);
    - NEEDS_REVIEW khi có thuốc không dựng được lịch an toàn;
    - ACTIVE khi toàn bộ đơn đã có khung giờ hợp lệ.
    """
    started = time.perf_counter()
    result = await planning_agent.ainvoke({"prescription": prescription, "routine": routine})
    latency_ms = int((time.perf_counter() - started) * 1000)

    error = result.get("error")
    review_notes: list[str] = list(result.get("review_notes", []))
    slots = result.get("slots", [])

    if error:
        status = ScheduleStatus.FAILED
        review_notes = [error]
        slots = []
    elif review_notes:
        status = ScheduleStatus.NEEDS_REVIEW
    else:
        status = ScheduleStatus.ACTIVE

    return MedicationSchedule(
        id=schedule_id,
        patient_id=prescription.patient_id,
        prescription_id=prescription.id,
        status=status,
        slots=slots,
        review_notes=review_notes,
        agent_run=AgentRun(
            id=f"run_{uuid.uuid4().hex[:8]}",
            status=status,
            latency_ms=latency_ms,
        ),
    )
