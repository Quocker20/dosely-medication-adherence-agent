"""Domain models cho RemindRx (VMEC-04).

Đặt tên trường bám theo mục 7.4 (Data dictionary) và mục 8 (API spec) trong
docs/RemindRx_Tong_Hop_Tai_Lieu.md. Không đưa logic nghiệp vụ vào đây —
validator nằm ở src/services/prescription_validator.py.
"""

from __future__ import annotations

import re
from enum import StrEnum

from pydantic import BaseModel, Field, field_validator

HHMM = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")


class PrescriptionStatus(StrEnum):
    DRAFT = "DRAFT"
    APPROVED = "APPROVED"
    SUPERSEDED = "SUPERSEDED"
    ENDED = "ENDED"
    CANCELLED = "CANCELLED"


class ScheduleStatus(StrEnum):
    GENERATING = "GENERATING"
    ACTIVE = "ACTIVE"
    SUPERSEDED = "SUPERSEDED"
    FAILED = "FAILED"
    NEEDS_REVIEW = "NEEDS_REVIEW"


class DoseStatus(StrEnum):
    PENDING = "PENDING"
    SENT = "SENT"
    TAKEN = "TAKEN"
    LATE = "LATE"
    SKIPPED = "SKIPPED"
    MISSED = "MISSED"
    CANCELLED = "CANCELLED"


class DoseAction(StrEnum):
    """Ba hành động bệnh nhân được phép ghi nhận cho một cữ thuốc."""

    TAKEN = "TAKEN"
    LATE = "LATE"
    SKIPPED = "SKIPPED"


class SymptomSeverity(StrEnum):
    MILD = "MILD"
    MODERATE = "MODERATE"
    SEVERE = "SEVERE"


class AlertState(StrEnum):
    OPEN = "OPEN"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    ESCALATING = "ESCALATING"
    RESOLVED = "RESOLVED"
    CLOSED_FALSE_POSITIVE = "CLOSED_FALSE_POSITIVE"


class AlertKind(StrEnum):
    MISSED_STREAK = "MISSED_STREAK"
    SOS = "SOS"
    SEVERE_SYMPTOM = "SEVERE_SYMPTOM"


class PatientStatus(StrEnum):
    RED_ALERT = "RED_ALERT"
    SOS = "SOS"
    WATCH = "WATCH"
    STABLE = "STABLE"


class Timing(StrEnum):
    """Thời điểm uống bác sĩ chọn — neo vào lịch sinh hoạt bệnh nhân."""

    BEFORE_BREAKFAST = "BEFORE_BREAKFAST"
    AFTER_BREAKFAST = "AFTER_BREAKFAST"
    AFTER_LUNCH = "AFTER_LUNCH"
    AFTER_DINNER = "AFTER_DINNER"
    BEDTIME = "BEDTIME"


class PatientRoutine(BaseModel):
    """Giờ sinh hoạt — đầu vào của Planning Agent, không phải dữ liệu lâm sàng."""

    wake: str = "06:00"
    breakfast: str = "07:00"
    lunch: str = "12:00"
    dinner: str = "18:30"
    sleep: str = "22:00"

    @field_validator("wake", "breakfast", "lunch", "dinner", "sleep")
    @classmethod
    def _hhmm(cls, v: str) -> str:
        if not HHMM.match(v):
            raise ValueError("giờ phải theo định dạng HH:MM (24h)")
        return v


class LastEvent(BaseModel):
    text: str
    tone: str = "ok"  # ok | warn | crit
    at: str


class Patient(BaseModel):
    id: str
    name: str
    initials: str
    age: int = Field(ge=0, le=130)
    diagnosis: str
    routine: PatientRoutine
    adherence_7d: list[int] = Field(default_factory=list)
    adherence_rate: int = Field(ge=0, le=100)
    status: PatientStatus
    symptom: str = "Không"
    consecutive_miss: int = 0
    last_event: LastEvent


class AdherenceLog(BaseModel):
    at: str
    status: DoseStatus | None = None
    message: str


class WeekCell(BaseModel):
    """Một ô trong lưới tuân thủ 7 ngày (2 hàng: sáng/tối)."""

    row: str
    day: int = Field(ge=0, le=6)
    status: DoseStatus


class PatientDetail(BaseModel):
    patient: Patient
    routine: PatientRoutine
    logs: list[AdherenceLog]
    week: list[WeekCell]


class PrescriptionItemIn(BaseModel):
    drug_name: str = Field(default="", max_length=200)
    dose_per_intake: str = Field(default="", max_length=100)
    frequency_per_day: int = Field(default=1, ge=0, le=99)
    timing: Timing = Timing.AFTER_BREAKFAST
    treatment_days: int = Field(default=30, ge=0, le=3650)
    patient_note: str = Field(default="", max_length=500)


class PrescriptionItem(PrescriptionItemIn):
    seq: int


class PrescriptionCreate(BaseModel):
    items: list[PrescriptionItemIn] = Field(default_factory=list)


class Prescription(BaseModel):
    id: str
    patient_id: str
    doctor_id: str
    status: PrescriptionStatus
    version: int = 1
    created_at: str
    approved_at: str | None = None
    items: list[PrescriptionItem]


class ValidationIssue(BaseModel):
    code: str
    field: str
    message: str
    item_seq: int | None = None


class ValidationReport(BaseModel):
    ok: bool
    issues: list[ValidationIssue] = Field(default_factory=list)


class ScheduledDose(BaseModel):
    id: str = ""
    drug_name: str
    dose_per_intake: str
    treatment_days: int
    patient_note: str = ""
    status: DoseStatus = DoseStatus.PENDING


class ScheduleSlot(BaseModel):
    time: str
    doses: list[ScheduledDose]


class AgentRun(BaseModel):
    """Bản ghi audit cho một lần chạy agent (mục 7.2)."""

    id: str
    graph: str = "planning_agent"
    status: ScheduleStatus
    latency_ms: int
    scope: list[str] = Field(default_factory=lambda: ["COMPUTE_REMINDER_TIMES"])
    denied_ops: list[str] = Field(
        default_factory=lambda: [
            "UPDATE_DOSE",
            "UPDATE_FREQUENCY",
            "UPDATE_ROUTE",
            "UPDATE_DURATION",
        ]
    )


class MedicationSchedule(BaseModel):
    id: str
    patient_id: str
    prescription_id: str
    status: ScheduleStatus
    version: int = 1
    slots: list[ScheduleSlot] = Field(default_factory=list)
    review_notes: list[str] = Field(default_factory=list)
    agent_run: AgentRun


class GenerateScheduleRequest(BaseModel):
    prescription_id: str


class DoseActionRequest(BaseModel):
    action: DoseAction
    note: str = Field(default="", max_length=500)


class DoseActionRecord(BaseModel):
    id: str
    dose_id: str
    patient_id: str
    status: DoseAction
    note: str = ""
    recorded_at: str


class AdherenceSummary(BaseModel):
    patient_id: str
    adherence_rate: int = Field(ge=0, le=100)
    taken: int = 0
    late: int = 0
    skipped: int = 0
    missed: int = 0
    pending: int = 0


class HealthSurveyCreate(BaseModel):
    mood: int = Field(ge=1, le=5)
    symptoms: list[str] = Field(default_factory=list, max_length=20)
    severity: SymptomSeverity
    note: str = Field(default="", max_length=500)


class HealthSurvey(BaseModel):
    id: str
    patient_id: str
    mood: int
    symptoms: list[str]
    severity: SymptomSeverity
    note: str = ""
    submitted_at: str


class SosCreate(BaseModel):
    note: str = Field(default="", max_length=500)
    share_location: bool = False


class SosEvent(BaseModel):
    id: str
    patient_id: str
    note: str = ""
    share_location: bool
    created_at: str
    alert_id: str


class AlertChannel(BaseModel):
    name: str
    status: str  # QUEUED | SENT | DELIVERED | FAILED


class Alert(BaseModel):
    id: str
    kind: AlertKind
    patient_id: str
    title: str
    detail: str
    opened_at: str
    state: AlertState
    channels: list[AlertChannel]
    dispatch_ms: int


class AlertResolveRequest(BaseModel):
    false_positive: bool = False
    note: str = Field(default="", max_length=500)


class DashboardSummary(BaseModel):
    patients_total: int
    adherence_avg: int
    response_minutes: int
    open_alerts: int
    doses_missed_today: int
    doses_due_today: int
    red_alert_precision: int


class DrugCatalogEntry(BaseModel):
    drug_id: str
    brand_name: str
