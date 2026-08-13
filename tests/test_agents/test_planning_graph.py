import pytest

from src.agents.nodes.planning_node import validate_candidate_node
from src.agents.planning_graph import run_planning
from src.modules.planning.core.clinical import (
    PatientRoutine,
    Prescription,
    PrescriptionItem,
    PrescriptionItemIn,
    PrescriptionStatus,
    ScheduleStatus,
    Timing,
)

ROUTINE = PatientRoutine(wake="05:30", breakfast="06:45", lunch="11:45", dinner="18:15", sleep="21:30")


def _prescription(items: list[dict], status: PrescriptionStatus = PrescriptionStatus.APPROVED) -> Prescription:
    return Prescription(
        id="RX-1",
        patient_id="p-01",
        doctor_id="dr-1",
        status=status,
        created_at="2026-08-06T00:00:00+00:00",
        items=[PrescriptionItem(seq=index + 1, **item) for index, item in enumerate(items)],
    )


ONCE_DAILY = {
    "drug_name": "Amlodipin 5mg",
    "dose_per_intake": "1 viên",
    "frequency_per_day": 1,
    "timing": Timing.AFTER_BREAKFAST,
    "treatment_days": 30,
}


@pytest.mark.asyncio
async def test_schedule_anchored_to_patient_routine():
    schedule = await run_planning(_prescription([ONCE_DAILY]), ROUTINE, "SCH-1")

    assert schedule.status is ScheduleStatus.ACTIVE
    assert [slot.time for slot in schedule.slots] == ["07:15"]
    assert schedule.slots[0].doses[0].dose_per_intake == "1 viên"
    assert schedule.review_notes == []


@pytest.mark.asyncio
async def test_twice_daily_uses_breakfast_and_dinner_anchors():
    twice = {**ONCE_DAILY, "drug_name": "Losartan 50mg", "frequency_per_day": 2}
    schedule = await run_planning(_prescription([twice]), ROUTINE, "SCH-1")

    assert [slot.time for slot in schedule.slots] == ["07:15", "18:45"]


@pytest.mark.asyncio
async def test_draft_prescription_never_generates_schedule():
    schedule = await run_planning(_prescription([ONCE_DAILY], PrescriptionStatus.DRAFT), ROUTINE, "SCH-1")

    assert schedule.status is ScheduleStatus.FAILED
    assert schedule.slots == []
    assert "APPROVED" in schedule.review_notes[0]


@pytest.mark.asyncio
async def test_bedtime_with_multiple_intakes_needs_review():
    conflicting = {**ONCE_DAILY, "frequency_per_day": 2, "timing": Timing.BEDTIME}
    schedule = await run_planning(_prescription([conflicting]), ROUTINE, "SCH-1")

    assert schedule.status is ScheduleStatus.NEEDS_REVIEW
    assert schedule.slots == []
    assert "không tạo được 2 cữ" in schedule.review_notes[0]


@pytest.mark.asyncio
async def test_partial_conflict_keeps_valid_items_and_flags_review():
    conflicting = {**ONCE_DAILY, "drug_name": "Losartan 50mg", "frequency_per_day": 2, "timing": Timing.BEDTIME}
    schedule = await run_planning(_prescription([ONCE_DAILY, conflicting]), ROUTINE, "SCH-1")

    assert schedule.status is ScheduleStatus.NEEDS_REVIEW
    assert [slot.time for slot in schedule.slots] == ["07:15"]
    assert len(schedule.review_notes) == 1


@pytest.mark.asyncio
async def test_agent_run_records_scope_and_denied_ops():
    schedule = await run_planning(_prescription([ONCE_DAILY]), ROUTINE, "SCH-1")

    assert schedule.agent_run.scope == ["COMPUTE_REMINDER_TIMES"]
    assert "UPDATE_DOSE" in schedule.agent_run.denied_ops
    assert schedule.agent_run.latency_ms >= 0


@pytest.mark.asyncio
async def test_validator_rejects_candidate_that_mutates_dose():
    """Guardrail: nếu node sinh candidate đổi liều thì cổng validator chặn lại."""
    prescription = _prescription([ONCE_DAILY])
    mutated = PrescriptionItemIn(**{**ONCE_DAILY, "dose_per_intake": "2 viên"})

    result = await validate_candidate_node(
        {
            "prescription": prescription,
            "candidates": [{"seq": 1, "times": ["07:15"], "item": mutated}],
            "review_notes": [],
        }
    )

    assert "agent đổi dose_per_intake" in result["error"]
    assert result["candidates"] == []


@pytest.mark.asyncio
async def test_doses_closer_than_min_gap_are_dropped():
    """Ăn trưa sát bữa tối -> khoảng cách < 4 giờ -> không lên lịch, chờ bác sĩ."""
    packed = PatientRoutine(wake="06:00", breakfast="07:00", lunch="12:00", dinner="14:00", sleep="22:00")
    three_times = {**ONCE_DAILY, "frequency_per_day": 3}

    schedule = await run_planning(_prescription([three_times]), packed, "SCH-1")

    assert schedule.status is ScheduleStatus.NEEDS_REVIEW
    assert schedule.slots == []
    assert "dưới ngưỡng an toàn" in schedule.review_notes[0]
