"""Stage 5 — remedy classification for the nightly graded-adherence review.

One structured LLM call, no LangGraph (see plan Stage 5.3: `AgentState` is
chat-shaped and does not fit a single classify-and-explain call with no
conditional edges). Rules (service.py) already decided severity before this
module ever runs; there is structurally no field in RemedyAnalysis through
which the model could change it, and this module never writes to the
database at all -- both the transaction-isolation guardrail (5.2, "never
called inside a DB transaction") and the "severity is rules-only" guarantee
hold by construction, not by convention.

De-identification: the prompt built here carries only clinical counts and a
severity label, never patient_id, name, phone, or DOB -- there is nothing in
_build_prompt that could leak identity even by mistake, since the indicator
dataclasses it reads (SlotBreakdown, MedicationBreakdown, SymptomEvidence)
never carried identity fields to begin with.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass
from enum import Enum
from typing import FrozenSet, List, Literal, Optional

from pydantic import BaseModel, Field

from src.agents.medication_policy import MEDICATION_RULES, fold
from src.core.config import Settings
from src.modules.adherence_review.repository import (
    MedicationBreakdown,
    SlotBreakdown,
    SymptomEvidence,
)
from src.modules.adherence_review.enums import Action, Severity
from src.modules.planning.core.llm import get_llm

logger = logging.getLogger(__name__)


class RemedyClass(str, Enum):
    RESCHEDULE_TIMING = "RESCHEDULE_TIMING"
    SUSPECTED_SIDE_EFFECT = "SUSPECTED_SIDE_EFFECT"
    DELIBERATE_REFUSAL = "DELIBERATE_REFUSAL"
    DISENGAGEMENT = "DISENGAGEMENT"
    EXTERNAL_DISRUPTION = "EXTERNAL_DISRUPTION"
    UNCLEAR = "UNCLEAR"


class RemedyAnalysis(BaseModel):
    """Structured output of the one LLM call this module makes.

    reasoning_doctor is Optional here, not `str` as the plan's sketch shows
    -- the plan's own fallback rule sets it to None on timeout/error, which
    a non-optional str field cannot represent. Storage already expects this:
    adherence_reviews.llm_reasoning (migration 0022) is a nullable TEXT
    column.
    """

    remedy_class: RemedyClass
    confidence: Literal["high", "medium", "low"]
    reasoning_doctor: Optional[str] = Field(default=None, max_length=600)
    message_patient: Optional[str] = Field(default=None, max_length=240)


# Public (not module-private): Stage 6's orchestrator reuses this exact same
# shape for patients dropped by the max-LLM-calls cap (5.2/6.5) -- a capped
# patient still gets a review row and the rule-decided action, just without
# an attempted classification, identical to a timeout/error outcome.
FALLBACK_REMEDY_ANALYSIS = RemedyAnalysis(
    remedy_class=RemedyClass.UNCLEAR,
    confidence="low",
    reasoning_doctor=None,
    message_patient=None,
)


@dataclass(frozen=True)
class RemedyContext:
    """Remedy-side indicators for one patient's nightly review -- the
    numbers Stage 3 computed that feed the LLM, never the severity rules.
    Deliberately excludes patient identity and free-text survey fields
    (answers_json, symptom description) per Stage 3's own exclusion."""

    severity: Severity
    skipped_count: int
    missed_count: int
    trend_delta: Optional[float]
    slot_breakdown: List[SlotBreakdown]
    medication_breakdown: List[MedicationBreakdown]
    symptom_evidence: List[SymptomEvidence]


_SYSTEM_PROMPT = """Bạn phân tích số liệu tuân thủ uống thuốc của MỘT bệnh nhân trong cửa sổ thời gian gần đây để phân loại nguyên nhân nhiều khả năng nhất. Đây là bước hỗ trợ bác sĩ, không phải tư vấn trực tiếp cho bệnh nhân.

QUY TẮC BẮT BUỘC:
- CHỈ trích dẫn các số liệu được cung cấp bên dưới. Không suy diễn thêm chẩn đoán, không giả định tiền sử bệnh, không bịa thêm chi tiết.
- Mức độ nghiêm trọng (severity) đã được hệ thống xác định trước bằng luật cố định — không được thay đổi, không được đề cập lại như một đề xuất.
- TUYỆT ĐỐI KHÔNG đề cập liều lượng cụ thể, không đề xuất tăng/giảm/ngừng/đổi thuốc dưới bất kỳ hình thức nào.
- Nếu số liệu không cho thấy nguyên nhân rõ ràng, chọn remedy_class="UNCLEAR" thay vì đoán — một suy đoán sai còn tệ hơn không có suy đoán.

CHỌN ĐÚNG MỘT NHÓM NGUYÊN NHÂN:
- RESCHEDULE_TIMING: liều bị bỏ lỡ tập trung rõ vào một khung giờ cụ thể trong ngày.
- SUSPECTED_SIDE_EFFECT: liều bị bỏ lỡ tập trung rõ vào một loại thuốc cụ thể, kèm triệu chứng được báo cáo gần đây.
- DELIBERATE_REFUSAL: số liều chủ động đánh dấu bỏ qua (SKIPPED) cao hơn rõ rệt so với số liều quên/quá giờ (MISSED).
- DISENGAGEMENT: liều bị quên/quá giờ (MISSED) rải rác, không tập trung vào khung giờ hay loại thuốc nào, không có triệu chứng liên quan.
- EXTERNAL_DISRUPTION: tuân thủ giảm đột ngột so với giai đoạn trước đó, không có mẫu hình bất thường nào khác.
- UNCLEAR: không nhóm nào ở trên phù hợp rõ ràng với số liệu.

ĐẦU RA:
- reasoning_doctor: tối đa vài câu ngắn dành cho bác sĩ, PHẢI nêu số liệu cụ thể làm căn cứ cho lựa chọn.
- message_patient: một câu nhắc nhở ngắn, nhẹ nhàng, không dùng thuật ngữ y khoa, không đề cập liều lượng hay tên thuốc cụ thể, không đề nghị các việc ứng dụng đã tự làm sẵn (ứng dụng đã tự nhắc giờ uống thuốc) — chỉ gợi ý hành động đơn giản mà bệnh nhân cần tự làm (ví dụ: để thuốc ở nơi dễ thấy, nhờ người thân nhắc, trao đổi với bác sĩ ở lần tái khám). Để trống nếu không có gợi ý phù hợp.
"""


def _build_prompt(context: RemedyContext) -> str:
    lines: List[str] = [
        f"Mức độ nghiêm trọng đã xác định trước (KHÔNG thay đổi, chỉ dùng làm bối cảnh): {context.severity.value}",
        f"Số liều chủ động bỏ qua (SKIPPED): {context.skipped_count}",
        f"Số liều quên/quá giờ (MISSED): {context.missed_count}",
    ]
    if context.trend_delta is not None:
        lines.append(
            f"Thay đổi tỷ lệ tuân thủ so với giai đoạn trước: {context.trend_delta:+.1f} điểm phần trăm"
        )
    if context.slot_breakdown:
        lines.append("Phân bố theo khung giờ (tổng liều / số liều bỏ lỡ):")
        for slot in context.slot_breakdown:
            lines.append(f"  - {slot.dose_slot}: {slot.total} liều, {slot.missed} bỏ lỡ")
    if context.medication_breakdown:
        lines.append("Phân bố theo loại thuốc (tổng liều / số liều bỏ lỡ):")
        for med in context.medication_breakdown:
            lines.append(f"  - {med.display_name}: {med.total} liều, {med.missed} bỏ lỡ")
    if context.symptom_evidence:
        lines.append("Triệu chứng được báo cáo trong khảo sát sức khỏe gần đây:")
        for symptom in context.symptom_evidence:
            lines.append(
                f"  - {symptom.survey_date.isoformat()}: {symptom.symptom_code} (mức độ {symptom.severity})"
            )
    return "\n".join(lines)


def _contains_prescribing_language(text: str) -> bool:
    """Reject-list scan only -- deliberately NOT match_medication_decision.

    match_medication_decision (src/agents/medication_policy.py) requires a
    first-person marker ("tôi", "mình", ...) alongside a decision marker,
    because it classifies a PATIENT's own question ("tôi có nên tăng liều
    không"). A model-generated leak reads as a statement or instruction
    ("nên tăng liều"), not a first-person question, so that gating would
    let a real leak through undetected. This checks the raw keyword lists
    from MEDICATION_RULES alone, with no personal-marker requirement --
    broader and fail-closed on purpose: a false positive here only costs
    one dropped message, not a shipped dosage instruction.
    """
    normalized = fold(text)
    return any(marker in normalized for _, markers in MEDICATION_RULES for marker in markers)


def enforce_patient_message_gate(
    analysis: RemedyAnalysis, actions: FrozenSet[Action]
) -> RemedyAnalysis:
    """Patient-facing text survives only if tonight's rule-decided actions
    (resolve_action's output, computed independently in service.py) actually
    include PATIENT_NOTIFICATION -- enforced here structurally rather than
    trusting the model to only fill the field in when appropriate. Call this
    from whichever code persists the nightly review (Stage 6), after
    resolve_action has already run."""
    if analysis.message_patient is not None and Action.PATIENT_NOTIFICATION not in actions:
        return analysis.model_copy(update={"message_patient": None})
    return analysis


async def classify_remedy(
    patient_id: uuid.UUID, context: RemedyContext, cfg: Settings
) -> RemedyAnalysis:
    """The one LLM call this module makes. Never touches the database --
    the caller is responsible for calling this only after its read
    transaction has committed and closed, and before opening the write
    transaction that persists the result (plan 5.2's "never inside a DB
    transaction" guardrail).

    On timeout or any exception, falls back to UNCLEAR/low/None and still
    lets the caller proceed with the rule-decided severity and action --
    a model outage degrades the explanation, never the alert. Logged at
    warning level so a rising fallback rate is visible in the same place
    every other fail-open path in this codebase logs to (see
    src/core/cache.py for the same pattern).
    """
    prompt = _build_prompt(context)
    try:
        llm = get_llm().with_structured_output(RemedyAnalysis)
        result = await asyncio.wait_for(
            llm.ainvoke([("system", _SYSTEM_PROMPT), ("user", prompt)]),
            timeout=cfg.adherence_review_llm_timeout_seconds,
        )
    except Exception:  # noqa: BLE001 -- fail-open by design, see docstring
        logger.warning(
            "Adherence remedy classification failed for patient %s; falling back to UNCLEAR",
            patient_id,
            exc_info=True,
        )
        return FALLBACK_REMEDY_ANALYSIS

    analysis = result if isinstance(result, RemedyAnalysis) else RemedyAnalysis.model_validate(result)
    if analysis.message_patient and _contains_prescribing_language(analysis.message_patient):
        logger.warning(
            "Dropping LLM patient message for %s: matched a prescribing-language marker",
            patient_id,
        )
        analysis = analysis.model_copy(update={"message_patient": None})
    return analysis
