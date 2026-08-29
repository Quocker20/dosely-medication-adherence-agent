"""Stage 5: RemedyAnalysis contract, classify_remedy's fail-open guardrails,
the prescribing-language reject-list, and the patient-message routing gate.

No real LLM calls -- get_llm is patched the same way
tests/test_agents/test_rescheduling_node.py mocks with_structured_output.
"""
import asyncio
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from pydantic import ValidationError

from src.modules.adherence_review.llm import (
    RemedyAnalysis,
    RemedyClass,
    RemedyContext,
    classify_remedy,
    enforce_patient_message_gate,
)
from src.modules.adherence_review.repository import MedicationBreakdown, SlotBreakdown
from src.modules.adherence_review.service import Action, Severity

PATIENT_ID = uuid.uuid4()


def _cfg(**overrides) -> SimpleNamespace:
    defaults = dict(adherence_review_llm_timeout_seconds=5)
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _context(**overrides) -> RemedyContext:
    defaults = dict(
        severity=Severity.MODERATE,
        skipped_count=0,
        missed_count=3,
        trend_delta=None,
        slot_breakdown=[],
        medication_breakdown=[],
        symptom_evidence=[],
    )
    defaults.update(overrides)
    return RemedyContext(**defaults)


def _mock_llm_returning(value_or_exception):
    patcher = patch("src.modules.adherence_review.llm.get_llm")
    mock_get_llm = patcher.start()
    if isinstance(value_or_exception, Exception):
        mock_get_llm.return_value.with_structured_output.return_value.ainvoke = AsyncMock(
            side_effect=value_or_exception
        )
    else:
        mock_get_llm.return_value.with_structured_output.return_value.ainvoke = AsyncMock(
            return_value=value_or_exception
        )
    return patcher


# ---------------------------------------------------------------------------
# RemedyAnalysis contract
# ---------------------------------------------------------------------------


class TestRemedyAnalysisContract:
    def test_rejects_a_class_outside_the_enum(self):
        with pytest.raises(ValidationError):
            RemedyAnalysis(remedy_class="SOMETHING_ELSE", confidence="high", reasoning_doctor="x")

    def test_rejects_a_confidence_outside_the_three_levels(self):
        with pytest.raises(ValidationError):
            RemedyAnalysis(remedy_class=RemedyClass.UNCLEAR, confidence="certain", reasoning_doctor="x")

    def test_reasoning_doctor_over_length_is_rejected(self):
        with pytest.raises(ValidationError):
            RemedyAnalysis(
                remedy_class=RemedyClass.UNCLEAR, confidence="low", reasoning_doctor="x" * 601
            )

    def test_message_patient_over_length_is_rejected(self):
        with pytest.raises(ValidationError):
            RemedyAnalysis(
                remedy_class=RemedyClass.UNCLEAR,
                confidence="low",
                reasoning_doctor="x",
                message_patient="x" * 241,
            )

    def test_reasoning_doctor_can_be_none(self):
        """The plan's own fallback sets reasoning_doctor=None -- the field
        must be Optional to represent that, unlike the plan's literal `str`
        sketch. See the module docstring for why this deviates."""
        analysis = RemedyAnalysis(remedy_class=RemedyClass.UNCLEAR, confidence="low", reasoning_doctor=None)
        assert analysis.reasoning_doctor is None

    def test_has_no_severity_field_at_all(self):
        """Structural guarantee, not a convention: severity cannot appear
        in this schema, so there is no field through which the model could
        report a different severity than the rules already decided."""
        assert "severity" not in RemedyAnalysis.model_fields


# ---------------------------------------------------------------------------
# classify_remedy: success + fail-open guardrails
# ---------------------------------------------------------------------------


class TestClassifyRemedySuccess:
    @pytest.mark.asyncio
    async def test_returns_the_llm_result_unchanged(self):
        expected = RemedyAnalysis(
            remedy_class=RemedyClass.RESCHEDULE_TIMING,
            confidence="high",
            reasoning_doctor="Bỏ lỡ tập trung vào buổi tối.",
            message_patient="Thử đặt báo thức buổi tối nhé.",
        )
        patcher = _mock_llm_returning(expected)
        try:
            result = await classify_remedy(PATIENT_ID, _context(), _cfg())
        finally:
            patcher.stop()
        assert result == expected


class TestClassifyRemedyFailsOpen:
    @pytest.mark.asyncio
    async def test_timeout_falls_back_to_unclear_and_does_not_raise(self):
        async def _hangs(*args, **kwargs):
            await asyncio.sleep(10)

        patcher = patch("src.modules.adherence_review.llm.get_llm")
        mock_get_llm = patcher.start()
        mock_get_llm.return_value.with_structured_output.return_value.ainvoke = _hangs
        try:
            result = await classify_remedy(PATIENT_ID, _context(), _cfg(adherence_review_llm_timeout_seconds=0.05))
        finally:
            patcher.stop()
        assert result.remedy_class == RemedyClass.UNCLEAR
        assert result.confidence == "low"
        assert result.reasoning_doctor is None
        assert result.message_patient is None

    @pytest.mark.asyncio
    async def test_arbitrary_exception_falls_back_to_unclear_and_does_not_raise(self):
        patcher = _mock_llm_returning(RuntimeError("upstream API error"))
        try:
            result = await classify_remedy(PATIENT_ID, _context(), _cfg())
        finally:
            patcher.stop()
        assert result.remedy_class == RemedyClass.UNCLEAR
        assert result.message_patient is None

    @pytest.mark.asyncio
    async def test_fallback_never_raises_even_on_repeated_calls(self):
        """The fallback path must be safe to hit every night for a patient
        whose provider is down -- never once escalate to an unhandled
        exception that would abort the whole nightly batch."""
        patcher = _mock_llm_returning(RuntimeError("still down"))
        try:
            for _ in range(3):
                result = await classify_remedy(PATIENT_ID, _context(), _cfg())
                assert result.remedy_class == RemedyClass.UNCLEAR
        finally:
            patcher.stop()


# ---------------------------------------------------------------------------
# Prescribing-language reject-list
# ---------------------------------------------------------------------------


class TestPrescribingLanguageRejectList:
    @pytest.mark.asyncio
    async def test_dose_change_language_in_patient_message_is_scrubbed(self):
        leaked = RemedyAnalysis(
            remedy_class=RemedyClass.SUSPECTED_SIDE_EFFECT,
            confidence="medium",
            reasoning_doctor="Có vẻ liên quan tác dụng phụ.",
            message_patient="Bạn nên tăng liều thuốc buổi sáng.",
        )
        patcher = _mock_llm_returning(leaked)
        try:
            result = await classify_remedy(PATIENT_ID, _context(), _cfg())
        finally:
            patcher.stop()
        assert result.message_patient is None
        # Only the leaked field is scrubbed -- the rest of the analysis
        # survives, since the doctor-facing reasoning is not patient-facing.
        assert result.remedy_class == RemedyClass.SUSPECTED_SIDE_EFFECT
        assert result.reasoning_doctor == "Có vẻ liên quan tác dụng phụ."

    @pytest.mark.asyncio
    async def test_stop_medication_language_is_scrubbed(self):
        leaked = RemedyAnalysis(
            remedy_class=RemedyClass.DELIBERATE_REFUSAL,
            confidence="medium",
            reasoning_doctor="x",
            message_patient="Bạn có thể ngừng thuốc nếu thấy khó chịu.",
        )
        patcher = _mock_llm_returning(leaked)
        try:
            result = await classify_remedy(PATIENT_ID, _context(), _cfg())
        finally:
            patcher.stop()
        assert result.message_patient is None

    @pytest.mark.asyncio
    async def test_a_clean_reminder_message_survives(self):
        clean = RemedyAnalysis(
            remedy_class=RemedyClass.RESCHEDULE_TIMING,
            confidence="high",
            reasoning_doctor="x",
            message_patient="Thử đặt báo thức nhắc uống thuốc buổi tối nhé.",
        )
        patcher = _mock_llm_returning(clean)
        try:
            result = await classify_remedy(PATIENT_ID, _context(), _cfg())
        finally:
            patcher.stop()
        assert result.message_patient == "Thử đặt báo thức nhắc uống thuốc buổi tối nhé."


# ---------------------------------------------------------------------------
# enforce_patient_message_gate (the "routing layer" guardrail)
# ---------------------------------------------------------------------------


class TestEnforcePatientMessageGate:
    def test_drops_message_when_action_set_lacks_patient_notification(self):
        analysis = RemedyAnalysis(
            remedy_class=RemedyClass.RESCHEDULE_TIMING,
            confidence="high",
            reasoning_doctor="x",
            message_patient="Nhắc nhở nhẹ nhàng.",
        )
        gated = enforce_patient_message_gate(analysis, frozenset({Action.DOCTOR_WARNING}))
        assert gated.message_patient is None
        assert gated.remedy_class == RemedyClass.RESCHEDULE_TIMING

    def test_keeps_message_when_patient_notification_is_in_the_action_set(self):
        analysis = RemedyAnalysis(
            remedy_class=RemedyClass.RESCHEDULE_TIMING,
            confidence="high",
            reasoning_doctor="x",
            message_patient="Nhắc nhở nhẹ nhàng.",
        )
        gated = enforce_patient_message_gate(
            analysis, frozenset({Action.PATIENT_NOTIFICATION, Action.DOCTOR_WARNING})
        )
        assert gated.message_patient == "Nhắc nhở nhẹ nhàng."

    def test_none_message_stays_none_regardless_of_actions(self):
        analysis = RemedyAnalysis(remedy_class=RemedyClass.UNCLEAR, confidence="low", reasoning_doctor=None)
        gated = enforce_patient_message_gate(analysis, frozenset({Action.PATIENT_NOTIFICATION}))
        assert gated.message_patient is None


# ---------------------------------------------------------------------------
# RemedyContext / prompt construction sanity
# ---------------------------------------------------------------------------


class TestRemedyContextDoesNotCarryIdentity:
    def test_dataclass_fields_are_all_clinical_or_derived(self):
        """No patient_id, name, phone, or dob field exists on this
        dataclass at all -- a structural guarantee that classify_remedy's
        prompt-builder cannot leak identity, not a runtime check."""
        field_names = set(RemedyContext.__dataclass_fields__.keys())
        assert field_names == {
            "severity", "skipped_count", "missed_count", "trend_delta",
            "slot_breakdown", "medication_breakdown", "symptom_evidence",
        }

    @pytest.mark.asyncio
    async def test_prompt_is_built_from_context_without_error_for_full_data(self):
        """Smoke test: a context with every optional section populated
        must not raise while building the prompt (exercised indirectly via
        classify_remedy, since _build_prompt is a private helper)."""
        context = _context(
            trend_delta=-25.0,
            slot_breakdown=[SlotBreakdown(dose_slot="EVENING", total=5, missed=3)],
            medication_breakdown=[
                MedicationBreakdown(medication_id=uuid.uuid4(), display_name="Metformin", total=5, missed=2)
            ],
        )
        expected = RemedyAnalysis(remedy_class=RemedyClass.UNCLEAR, confidence="low", reasoning_doctor=None)
        patcher = _mock_llm_returning(expected)
        try:
            result = await classify_remedy(PATIENT_ID, context, _cfg())
        finally:
            patcher.stop()
        assert result == expected
