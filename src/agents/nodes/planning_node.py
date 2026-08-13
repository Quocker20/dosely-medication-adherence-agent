"""Node của Planning Agent (FR-2.1).

Vòng chạy: Input Gate → Normalize → Generate Candidate → Deterministic Validate
→ Persist (mục 7.2). Node sinh candidate là chỗ duy nhất được phép "đề xuất";
mọi thứ sau đó là code xác định.

Guardrail áp trong file này:
- chỉ đọc prescription có status=APPROVED;
- chỉ sinh THỜI ĐIỂM, không đụng dose/frequency/route/treatment_days;
- xung đột không giải được thì ghi review note, không tự bịa giờ khác.
"""

from __future__ import annotations

from typing import Any

from src.agents.state import PlanningState
from src.core.config import get_settings
from src.modules.planning.core.clinical import (
    PatientRoutine,
    Prescription,
    PrescriptionItem,
    PrescriptionItemIn,
    PrescriptionStatus,
    ScheduledDose,
    ScheduleSlot,
    Timing,
)
from src.modules.planning.core.prescription_validator import assert_clinical_fields_unchanged
from src.modules.planning.core.timekit import min_gap_minutes, shift, to_minutes

TIMING_LABELS: dict[Timing, str] = {
    Timing.BEFORE_BREAKFAST: "Trước ăn sáng",
    Timing.AFTER_BREAKFAST: "Sau ăn sáng",
    Timing.AFTER_LUNCH: "Sau ăn trưa",
    Timing.AFTER_DINNER: "Sau ăn tối",
    Timing.BEDTIME: "Trước khi ngủ",
}


def build_anchors(routine: PatientRoutine) -> dict[str, str]:
    """Neo thời điểm uống vào giờ sinh hoạt thật của bệnh nhân."""
    return {
        Timing.BEFORE_BREAKFAST.value: shift(routine.breakfast, -30),
        Timing.AFTER_BREAKFAST.value: shift(routine.breakfast, 30),
        Timing.AFTER_LUNCH.value: shift(routine.lunch, 30),
        Timing.AFTER_DINNER.value: shift(routine.dinner, 30),
        Timing.BEDTIME.value: shift(routine.sleep, -30),
    }


def candidate_times(item: PrescriptionItem, anchors: dict[str, str], routine: PatientRoutine) -> list[str] | None:
    """Khung giờ đề xuất cho một thuốc. None = không dựng được, cần bác sĩ xem lại."""
    frequency = item.frequency_per_day

    if frequency == 1:
        return [anchors[item.timing.value]]

    # Không thể có nhiều hơn một cữ "trước khi ngủ" trong ngày.
    if item.timing is Timing.BEDTIME:
        return None

    if frequency == 2:
        return [anchors[Timing.AFTER_BREAKFAST.value], anchors[Timing.AFTER_DINNER.value]]
    if frequency == 3:
        return [
            anchors[Timing.AFTER_BREAKFAST.value],
            anchors[Timing.AFTER_LUNCH.value],
            anchors[Timing.AFTER_DINNER.value],
        ]
    if frequency == 4:
        return [
            anchors[Timing.BEFORE_BREAKFAST.value],
            anchors[Timing.AFTER_LUNCH.value],
            shift(routine.dinner, -60),
            anchors[Timing.BEDTIME.value],
        ]
    return None


async def input_gate_node(state: PlanningState) -> dict[str, Any]:
    """Chặn đầu vào: chỉ chạy trên đơn đã được bác sĩ duyệt."""
    prescription: Prescription | None = state.get("prescription")

    if prescription is None:
        return {"error": "Thiếu đơn thuốc đầu vào."}
    if prescription.status is not PrescriptionStatus.APPROVED:
        return {
            "error": (
                f"Đơn {prescription.id} đang ở trạng thái {prescription.status.value}. "
                "Planning Agent chỉ đọc đơn APPROVED."
            )
        }
    if state.get("routine") is None:
        return {"error": "Thiếu lịch sinh hoạt bệnh nhân."}
    return {}


async def normalize_node(state: PlanningState) -> dict[str, Any]:
    """Chuẩn hóa đầu vào thành các mốc giờ neo."""
    return {"anchors": build_anchors(state["routine"]), "review_notes": []}


async def generate_candidate_node(state: PlanningState) -> dict[str, Any]:
    """Đề xuất khung giờ cho từng thuốc.

    Trường lâm sàng được sao chép nguyên vẹn từ đơn — node này không có
    đường nào để sửa chúng.
    """
    prescription: Prescription = state["prescription"]
    anchors: dict[str, str] = state["anchors"]
    routine: PatientRoutine = state["routine"]

    candidates: list[dict[str, Any]] = []
    notes: list[str] = list(state.get("review_notes", []))

    for item in prescription.items:
        times = candidate_times(item, anchors, routine)
        if times is None:
            notes.append(
                f"{item.drug_name} — không tạo được {item.frequency_per_day} cữ cho thời điểm "
                f'"{TIMING_LABELS[item.timing]}".'
            )
            continue
        candidates.append(
            {
                "seq": item.seq,
                "times": sorted(times, key=to_minutes),
                "item": PrescriptionItemIn(**item.model_dump(exclude={"seq"})),
            }
        )

    return {"candidates": candidates, "review_notes": notes}


async def validate_candidate_node(state: PlanningState) -> dict[str, Any]:
    """Cổng cuối bằng code: khoảng cách liều + bất biến trường lâm sàng."""
    settings = get_settings()
    prescription: Prescription = state["prescription"]
    candidates: list[dict[str, Any]] = state.get("candidates", [])
    notes: list[str] = list(state.get("review_notes", []))

    mutations = assert_clinical_fields_unchanged(prescription, [c["item"] for c in candidates])
    if mutations:
        return {"error": "; ".join(issue.message for issue in mutations), "candidates": []}

    accepted: list[dict[str, Any]] = []
    for candidate in candidates:
        gap = min_gap_minutes(candidate["times"])
        if gap < settings.min_dose_gap_minutes:
            notes.append(
                f"{candidate['item'].drug_name} — hai cữ cách nhau {gap} phút, "
                f"dưới ngưỡng an toàn {settings.min_dose_gap_minutes // 60} giờ."
            )
            continue
        accepted.append(candidate)

    return {"candidates": accepted, "review_notes": notes}


async def build_slots_node(state: PlanningState) -> dict[str, Any]:
    """Gộp candidate đã qua validator thành các cữ theo giờ."""
    grouped: dict[str, list[ScheduledDose]] = {}

    for candidate in state.get("candidates", []):
        item: PrescriptionItemIn = candidate["item"]
        for time in candidate["times"]:
            grouped.setdefault(time, []).append(
                ScheduledDose(
                    drug_name=item.drug_name,
                    dose_per_intake=item.dose_per_intake,
                    treatment_days=item.treatment_days,
                    patient_note=item.patient_note,
                )
            )

    slots = [ScheduleSlot(time=time, doses=grouped[time]) for time in sorted(grouped, key=to_minutes)]
    return {"slots": slots}
