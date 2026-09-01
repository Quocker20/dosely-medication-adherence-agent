from unittest.mock import AsyncMock

import pytest
from langchain_core.messages import HumanMessage

from src.agents import prescribed_drug_resolver as resolver


def _state(reference_type, **analysis):
    return {
        "patient_id": "patient-from-jwt",
        "client_date": "2026-08-29",
        "intent_analysis": {"reference_type": reference_type, **analysis},
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("reference_type", "analysis", "expected"),
    [
        ("schedule_time", {"schedule_time": "07:30"}, "Morning Drug"),
        ("dose_period", {"dose_period": "evening"}, "Evening Drug"),
        ("recent_dose", {}, "Morning Drug"),
        ("next_dose", {}, "Evening Drug"),
        ("meal_relation", {"meal_relation": "AFTER_MEAL"}, "Evening Drug"),
    ],
)
async def test_schedule_references_resolve_from_authenticated_app_endpoint(
    monkeypatch, reference_type, analysis, expected
):
    backend = AsyncMock(
        return_value={
            "timezone": "Asia/Bangkok",
            "doses": [
                {
                    "medication_id": "m1",
                    "medication_name": "Morning Drug",
                    "dose_slot": "MORNING",
                    "current_scheduled_at": "2026-08-29T07:30:00+07:00",
                    "status": "TAKEN",
                    "meal_relation": "BEFORE_MEAL",
                },
                {
                    "medication_id": "m2",
                    "medication_name": "Evening Drug",
                    "dose_slot": "EVENING",
                    "current_scheduled_at": "2026-08-29T19:30:00+07:00",
                    "status": "PENDING",
                    "meal_relation": "AFTER_MEAL",
                },
            ],
        }
    )
    monkeypatch.setattr(resolver, "get", backend)
    result = await resolver.resolve_prescribed_drug(_state(reference_type, **analysis))
    assert result.status == resolver.ResolutionStatus.RESOLVED_ONE
    assert result.medications[0]["medication_name"] == expected
    backend.assert_awaited_once_with("/patients/patient-from-jwt/schedules", params={"date": "2026-08-29"})


@pytest.mark.asyncio
async def test_ambiguous_period_never_guesses(monkeypatch):
    monkeypatch.setattr(
        resolver,
        "get",
        AsyncMock(
            return_value={
                "doses": [
                    {"medication_id": "m1", "medication_name": "Drug A", "dose_slot": "MORNING"},
                    {"medication_id": "m2", "medication_name": "Drug B", "dose_slot": "MORNING"},
                ]
            }
        ),
    )
    result = await resolver.resolve_prescribed_drug(_state("dose_period", dose_period="morning"))
    assert result.status == resolver.ResolutionStatus.RESOLVED_MULTIPLE


@pytest.mark.asyncio
async def test_context_uses_only_previously_verified_medication():
    state = _state("recent_context")
    state["memory_context"] = {"current_medication": {"medication_id": "m1", "display_name": "Verified Drug"}}
    result = await resolver.resolve_prescribed_drug(state)
    assert result.status == resolver.ResolutionStatus.RESOLVED_ONE
    assert result.medications[0]["display_name"] == "Verified Drug"


@pytest.mark.asyncio
async def test_missing_context_requires_clarification():
    result = await resolver.resolve_prescribed_drug(_state("recent_context"))
    assert result.status == resolver.ResolutionStatus.CONTEXT_EXPIRED


@pytest.mark.asyncio
async def test_prescription_ordinal_uses_current_authenticated_prescription(monkeypatch):
    backend = AsyncMock(
        return_value={
            "medications": [
                {"medication_id": "m1", "display_name": "First"},
                {"medication_id": "m2", "display_name": "Second"},
            ]
        }
    )
    monkeypatch.setattr(resolver, "get", backend)
    result = await resolver.resolve_prescribed_drug(_state("prescription_ordinal", prescription_ordinal=2))
    assert result.medications[0]["display_name"] == "Second"
    backend.assert_awaited_once_with("/patients/me/medications/current", params={"as_of": "2026-08-29"})


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "question",
    [
        "thuốc 7h sáng có tác dụng gì?",
        "thuốc cữ 7h sáng có tác dụng gì?",
        "thuốc ở cữ 7 giờ sáng có tác dụng gì?",
        "thuốc lúc 07:00 có tác dụng gì?",
    ],
)
async def test_explicit_clock_time_overrides_phrase_sensitive_llm_reference(monkeypatch, question):
    backend = AsyncMock(
        return_value={
            "timezone": "Asia/Bangkok",
            "doses": [
                {
                    "medication_id": "m1",
                    "medication_name": "Morning Drug",
                    "dose_slot": "",
                    "current_scheduled_at": "2026-08-29T07:00:00+07:00",
                }
            ],
        }
    )
    monkeypatch.setattr(resolver, "get", backend)
    state = _state("dose_period", dose_period="morning")
    state["messages"] = [HumanMessage(content=question)]

    result = await resolver.resolve_prescribed_drug(state)

    assert result.status == resolver.ResolutionStatus.RESOLVED_ONE
    assert result.reference_type == "schedule_time"
    assert result.reference_value == "07:00"
