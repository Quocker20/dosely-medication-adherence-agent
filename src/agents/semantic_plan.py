"""Structured semantic plan selected by the LLM, never executed directly."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


SemanticTool = Literal[
    "get_schedule",
    "get_next_dose",
    "get_current_medications",
    "explain_current_medications",
    "resolve_prescribed_medication",
    "search_drug_information",
    "report_meal_shift",
    "record_adverse_event",
    "get_recent_adverse_event",
    "clarify",
    "general_response",
]


class SemanticSymptom(BaseModel):
    name: str
    severity: Literal["MILD", "MODERATE", "SEVERE"] = "MILD"
    onset: str | None = None
    description: str | None = None


class SemanticStep(BaseModel):
    id: str = Field(pattern=r"^step_[1-3]$")
    tool: SemanticTool
    purpose: str = Field(description="Mục đích riêng của bước này")
    date_reference: str | None = None
    schedule_time: str | None = None
    dose_period: Literal["morning", "noon", "evening", "bedtime"] | None = None
    statuses: list[Literal["PENDING", "TAKEN", "MISSED", "SKIPPED"]] = Field(default_factory=list)
    drug_name: str | None = None
    symptoms: list[SemanticSymptom] = Field(default_factory=list)
    drug_reference_type: Literal[
        "none", "drug_name", "schedule_time", "dose_period", "next_dose",
        "recent_dose", "meal_relation", "prescription_ordinal", "recent_context",
    ] = "none"
    topics: list[Literal[
        "identity", "indication", "administration", "adverse_effect", "interaction",
        "contraindication", "missed_dose", "storage", "precaution", "dose_status", "other",
    ]] = Field(default_factory=list)
    requested_action: Literal[
        "read", "explain", "check_status", "change_schedule", "change_treatment", "other"
    ] = "read"
    needs_clarification: bool = False
    clarifying_question: str | None = None
    confidence: float = Field(default=0.5, ge=0, le=1)


class SemanticPlan(BaseModel):
    purpose: str = Field(description="Mục đích tổng thể của tin nhắn cuối")
    steps: list[SemanticStep] = Field(min_length=1, max_length=3)
    confidence: float = Field(default=0.5, ge=0, le=1)


TOOL_TO_LEGACY_INTENT = {
    "get_schedule": "ask_schedule",
    "get_next_dose": "ask_next_dose",
    "get_current_medications": "ask_my_medications",
    "explain_current_medications": "explain_my_medications",
    "resolve_prescribed_medication": "ask_prescribed_drug_info",
    "search_drug_information": "ask_drug_info",
    "report_meal_shift": "report_meal_shift",
    "record_adverse_event": "report_adverse_event",
    "get_recent_adverse_event": "get_recent_adverse_event",
    "clarify": "clarify",
    "general_response": "general",
}
