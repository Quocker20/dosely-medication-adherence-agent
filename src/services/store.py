"""Kho dữ liệu in-memory cho bản demo RemindRx.

MVP chưa gắn PostgreSQL (repo chưa cài SQLAlchemy). Store này giữ đúng ranh giới
để sau thay bằng repository thật: API không tự sửa dict, chỉ gọi method ở đây.
Dữ liệu reset khi restart process — chấp nhận được cho demo, KHÔNG dùng cho
dữ liệu lâm sàng thật.
"""

from __future__ import annotations

import itertools
from datetime import UTC, datetime

from src.models.clinical import (
    AdherenceLog,
    AdherenceSummary,
    AgentRun,
    Alert,
    AlertChannel,
    AlertKind,
    AlertState,
    DoseAction,
    DoseActionRecord,
    DoseStatus,
    DrugCatalogEntry,
    HealthSurvey,
    HealthSurveyCreate,
    LastEvent,
    MedicationSchedule,
    Patient,
    PatientDetail,
    PatientRoutine,
    PatientStatus,
    Prescription,
    PrescriptionItem,
    PrescriptionStatus,
    ScheduledDose,
    ScheduleSlot,
    ScheduleStatus,
    SosCreate,
    SosEvent,
    SymptomSeverity,
    Timing,
    WeekCell,
)

DRUG_CATALOG = [
    "Amlodipin 5mg",
    "Losartan 50mg",
    "Metformin 500mg",
    "Atorvastatin 20mg",
    "Bisoprolol 2.5mg",
    "Furosemid 40mg",
    "Aspirin 81mg",
    "Gliclazid 30mg",
    "Enalapril 10mg",
    "Spironolacton 25mg",
]

_T = DoseStatus.TAKEN
_L = DoseStatus.LATE
_M = DoseStatus.MISSED


def _week(rows: dict[str, list[DoseStatus]]) -> list[WeekCell]:
    return [
        WeekCell(row=row, day=day, status=status) for row, cells in rows.items() for day, status in enumerate(cells)
    ]


def _seed_patients() -> list[Patient]:
    return [
        Patient(
            id="p-01",
            name="Trần Thị H.",
            initials="TH",
            age=72,
            diagnosis="Tăng huyết áp",
            routine=PatientRoutine(wake="05:30", breakfast="06:45", lunch="11:45", dinner="18:15", sleep="21:30"),
            adherence_7d=[72, 65, 58, 50, 44, 40, 41],
            adherence_rate=41,
            status=PatientStatus.RED_ALERT,
            symptom="Khó thở, chóng mặt",
            consecutive_miss=3,
            last_event=LastEvent(text="Bỏ qua 3 liều liên tiếp", tone="crit", at="hôm nay 12:00"),
        ),
        Patient(
            id="p-02",
            name="Lê Văn M.",
            initials="LV",
            age=80,
            diagnosis="Đái tháo đường",
            routine=PatientRoutine(wake="06:00", breakfast="07:00", lunch="12:00", dinner="18:30", sleep="22:00"),
            adherence_7d=[70, 68, 62, 60, 58, 56, 55],
            adherence_rate=55,
            status=PatientStatus.SOS,
            symptom="Đau ngực",
            consecutive_miss=1,
            last_event=LastEvent(text="Nhấn SOS lúc 19:01", tone="crit", at="hôm nay 19:01"),
        ),
        Patient(
            id="p-03",
            name="Phạm Thị L.",
            initials="PT",
            age=68,
            diagnosis="Rối loạn lipid",
            routine=PatientRoutine(wake="06:30", breakfast="07:15", lunch="12:15", dinner="18:45", sleep="22:30"),
            adherence_7d=[78, 76, 74, 72, 70, 69, 69],
            adherence_rate=69,
            status=PatientStatus.WATCH,
            symptom="Mệt mỏi",
            consecutive_miss=0,
            last_event=LastEvent(text="Uống muộn 45 phút", tone="warn", at="hôm nay 13:15"),
        ),
        Patient(
            id="p-04",
            name="Nguyễn Văn K.",
            initials="NV",
            age=75,
            diagnosis="Suy tim",
            routine=PatientRoutine(wake="05:45", breakfast="06:30", lunch="11:30", dinner="18:00", sleep="21:00"),
            adherence_7d=[90, 92, 93, 94, 95, 94, 94],
            adherence_rate=94,
            status=PatientStatus.STABLE,
            consecutive_miss=0,
            last_event=LastEvent(text="Đã uống 12:02", tone="ok", at="hôm nay 12:02"),
        ),
        Patient(
            id="p-05",
            name="Đỗ Thị N.",
            initials="ĐT",
            age=70,
            diagnosis="Tăng huyết áp",
            routine=PatientRoutine(wake="05:00", breakfast="06:15", lunch="11:30", dinner="17:45", sleep="21:00"),
            adherence_7d=[84, 85, 86, 88, 89, 88, 88],
            adherence_rate=88,
            status=PatientStatus.STABLE,
            consecutive_miss=0,
            last_event=LastEvent(text="Đã uống 06:35", tone="ok", at="hôm nay 06:35"),
        ),
    ]


def _seed_logs() -> dict[str, list[AdherenceLog]]:
    return {
        "p-01": [
            AdherenceLog(
                at="12:00", status=DoseStatus.MISSED, message="Losartan 50mg — MISSED sau 60 phút không phản hồi"
            ),
            AdherenceLog(
                at="07:30", status=DoseStatus.SKIPPED, message="Amlodipin 5mg — SKIPPED (bệnh nhân bấm Bỏ qua)"
            ),
            AdherenceLog(at="07:12", message="Khai báo triệu chứng: khó thở, chóng mặt (SEVERE)"),
        ],
        "p-02": [
            AdherenceLog(at="19:01", message="SOS một chạm — Red Alert đã mở"),
            AdherenceLog(at="12:30", status=DoseStatus.LATE, message="Metformin 500mg — LATE (trễ 38 phút)"),
            AdherenceLog(at="07:30", status=DoseStatus.TAKEN, message="Metformin 500mg — TAKEN"),
        ],
        "p-03": [
            AdherenceLog(at="13:15", status=DoseStatus.LATE, message="Atorvastatin 20mg — LATE (trễ 45 phút)"),
            AdherenceLog(at="07:35", status=DoseStatus.TAKEN, message="Atorvastatin 20mg — TAKEN"),
        ],
        "p-04": [
            AdherenceLog(at="12:02", status=DoseStatus.TAKEN, message="Furosemid 40mg — TAKEN"),
            AdherenceLog(at="06:58", status=DoseStatus.TAKEN, message="Bisoprolol 2.5mg — TAKEN"),
        ],
        "p-05": [
            AdherenceLog(at="06:35", status=DoseStatus.TAKEN, message="Amlodipin 5mg — TAKEN"),
            AdherenceLog(at="21:40", message="Khảo sát cuối ngày: không triệu chứng"),
        ],
    }


def _seed_week() -> dict[str, list[WeekCell]]:
    return {
        "p-01": _week({"Sáng": [_T, _T, _L, _M, _M, _M, _M], "Tối": [_T, _T, _T, _L, _M, _M, _M]}),
        "p-02": _week({"Sáng": [_T, _L, _T, _M, _T, _L, _T], "Tối": [_T, _M, _T, _T, _L, _M, _T]}),
        "p-03": _week({"Sáng": [_T, _L, _T, _T, _L, _T, _L], "Tối": [_T, _T, _L, _T, _T, _T, _L]}),
        "p-04": _week({"Sáng": [_T, _T, _T, _T, _T, _T, _T], "Tối": [_T, _T, _L, _T, _T, _T, _T]}),
        "p-05": _week({"Sáng": [_T, _T, _T, _L, _T, _T, _T], "Tối": [_T, _T, _T, _M, _T, _T, _T]}),
    }


def _seed_alerts() -> list[Alert]:
    return [
        Alert(
            id="AL-2081",
            kind=AlertKind.MISSED_STREAK,
            patient_id="p-01",
            title="Bỏ 3 liều liên tiếp trong ngày",
            detail=("Amlodipin 5mg 07:30 · Losartan 50mg 12:00 · Losartan 50mg 20:00 — không có phản hồi sau 60 phút."),
            opened_at="12:58",
            state=AlertState.OPEN,
            channels=[
                AlertChannel(name="Web Push", status="DELIVERED"),
                AlertChannel(name="Zalo người thân", status="DELIVERED"),
                AlertChannel(name="SMS người thân", status="SENT"),
                AlertChannel(name="Portal bác sĩ", status="DELIVERED"),
            ],
            dispatch_ms=4200,
        ),
        Alert(
            id="AL-2082",
            kind=AlertKind.SOS,
            patient_id="p-02",
            title="SOS một chạm từ bệnh nhân",
            detail='Bệnh nhân bấm SOS kèm ghi chú "đau ngực". Vị trí chia sẻ: không bật.',
            opened_at="19:01",
            state=AlertState.OPEN,
            channels=[
                AlertChannel(name="Call bot người thân", status="SENT"),
                AlertChannel(name="Zalo người thân", status="DELIVERED"),
                AlertChannel(name="Portal bác sĩ", status="DELIVERED"),
            ],
            dispatch_ms=3100,
        ),
        Alert(
            id="AL-2079",
            kind=AlertKind.SEVERE_SYMPTOM,
            patient_id="p-01",
            title="Triệu chứng mức SEVERE",
            detail="Khảo sát sáng: khó thở khi nằm, chóng mặt khi đứng dậy. Ghi nhận lúc 07:12.",
            opened_at="07:12",
            state=AlertState.ACKNOWLEDGED,
            channels=[
                AlertChannel(name="Portal bác sĩ", status="DELIVERED"),
                AlertChannel(name="SMS người thân", status="DELIVERED"),
            ],
            dispatch_ms=5600,
        ),
    ]


def _seed_prescriptions() -> list[Prescription]:
    """Đơn đã duyệt để app bệnh nhân có dữ liệu ngay sau khi backend khởi động."""

    return [
        Prescription(
            id="RX-2400",
            patient_id="p-02",
            doctor_id="doctor-demo-01",
            status=PrescriptionStatus.APPROVED,
            created_at="2026-08-03T08:00:00+00:00",
            approved_at="2026-08-03T08:05:00+00:00",
            items=[
                PrescriptionItem(
                    seq=1,
                    drug_name="Metformin 500mg",
                    dose_per_intake="1 viên",
                    frequency_per_day=3,
                    timing=Timing.AFTER_BREAKFAST,
                    treatment_days=14,
                    patient_note="Uống sau bữa ăn",
                ),
                PrescriptionItem(
                    seq=2,
                    drug_name="Losartan 50mg",
                    dose_per_intake="1 viên",
                    frequency_per_day=1,
                    timing=Timing.AFTER_LUNCH,
                    treatment_days=14,
                    patient_note="",
                ),
                PrescriptionItem(
                    seq=3,
                    drug_name="Atorvastatin 20mg",
                    dose_per_intake="1 viên",
                    frequency_per_day=1,
                    timing=Timing.BEDTIME,
                    treatment_days=14,
                    patient_note="",
                ),
            ],
        )
    ]


def _seed_schedules() -> list[MedicationSchedule]:
    return [
        MedicationSchedule(
            id="SCH-9100",
            patient_id="p-02",
            prescription_id="RX-2400",
            status=ScheduleStatus.ACTIVE,
            slots=[
                ScheduleSlot(
                    time="07:30",
                    doses=[
                        ScheduledDose(
                            id="dose-p02-0730-metformin",
                            drug_name="Metformin 500mg",
                            dose_per_intake="1 viên",
                            treatment_days=14,
                            patient_note="Uống sau bữa ăn",
                            status=DoseStatus.TAKEN,
                        )
                    ],
                ),
                ScheduleSlot(
                    time="12:30",
                    doses=[
                        ScheduledDose(
                            id="dose-p02-1230-metformin",
                            drug_name="Metformin 500mg",
                            dose_per_intake="1 viên",
                            treatment_days=14,
                            patient_note="Uống sau bữa ăn",
                        ),
                        ScheduledDose(
                            id="dose-p02-1230-losartan",
                            drug_name="Losartan 50mg",
                            dose_per_intake="1 viên",
                            treatment_days=14,
                        ),
                    ],
                ),
                ScheduleSlot(
                    time="18:30",
                    doses=[
                        ScheduledDose(
                            id="dose-p02-1830-metformin",
                            drug_name="Metformin 500mg",
                            dose_per_intake="1 viên",
                            treatment_days=14,
                            patient_note="Uống sau bữa ăn",
                        )
                    ],
                ),
                ScheduleSlot(
                    time="22:00",
                    doses=[
                        ScheduledDose(
                            id="dose-p02-2200-atorvastatin",
                            drug_name="Atorvastatin 20mg",
                            dose_per_intake="1 viên",
                            treatment_days=14,
                        )
                    ],
                ),
            ],
            agent_run=AgentRun(
                id="agent-seed-01",
                status=ScheduleStatus.ACTIVE,
                latency_ms=184,
            ),
        )
    ]


class Store:
    """Repository in-memory. Mọi thay đổi trạng thái đi qua đây."""

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self._patients: dict[str, Patient] = {p.id: p for p in _seed_patients()}
        self._logs = _seed_logs()
        self._week = _seed_week()
        self._alerts: dict[str, Alert] = {a.id: a for a in _seed_alerts()}
        self._prescriptions: dict[str, Prescription] = {p.id: p for p in _seed_prescriptions()}
        self._schedules: dict[str, MedicationSchedule] = {s.patient_id: s for s in _seed_schedules()}
        self._dose_actions: dict[str, DoseActionRecord] = {}
        self._dose_action_keys: dict[str, DoseActionRecord] = {}
        self._health_surveys: dict[str, HealthSurvey] = {}
        self._sos_events: dict[str, SosEvent] = {}
        self._sos_keys: dict[str, SosEvent] = {}
        self._rx_seq = itertools.count(2401)
        self._schedule_seq = itertools.count(9101)
        self._action_seq = itertools.count(1)
        self._survey_seq = itertools.count(1)
        self._sos_seq = itertools.count(1)
        self._alert_seq = itertools.count(2083)

    # ---------- patients ----------
    def list_patients(self) -> list[Patient]:
        order = {
            PatientStatus.RED_ALERT: 0,
            PatientStatus.SOS: 1,
            PatientStatus.WATCH: 2,
            PatientStatus.STABLE: 3,
        }
        return sorted(self._patients.values(), key=lambda p: (order[p.status], p.adherence_rate))

    def get_patient(self, patient_id: str) -> Patient | None:
        return self._patients.get(patient_id)

    def get_patient_detail(self, patient_id: str) -> PatientDetail | None:
        patient = self._patients.get(patient_id)
        if patient is None:
            return None
        return PatientDetail(
            patient=patient,
            routine=patient.routine,
            logs=self._logs.get(patient_id, []),
            week=self._week.get(patient_id, []),
        )

    def update_routine(self, patient_id: str, routine: PatientRoutine) -> Patient | None:
        patient = self._patients.get(patient_id)
        if patient is None:
            return None
        updated = patient.model_copy(update={"routine": routine})
        self._patients[patient_id] = updated
        return updated

    def logs_for(self, patient_id: str) -> list[AdherenceLog]:
        return self._logs.get(patient_id, [])

    # ---------- prescriptions ----------
    def next_prescription_id(self) -> str:
        return f"RX-{next(self._rx_seq)}"

    def save_prescription(self, prescription: Prescription) -> Prescription:
        self._prescriptions[prescription.id] = prescription
        return prescription

    def get_prescription(self, prescription_id: str) -> Prescription | None:
        return self._prescriptions.get(prescription_id)

    def list_prescriptions(self, patient_id: str) -> list[Prescription]:
        return [p for p in self._prescriptions.values() if p.patient_id == patient_id]

    # ---------- schedules ----------
    def next_schedule_id(self) -> str:
        return f"SCH-{next(self._schedule_seq)}"

    def save_schedule(self, schedule: MedicationSchedule) -> MedicationSchedule:
        """Lịch mới thay lịch cũ theo kiểu versioning, không sửa đè bản ghi cũ."""
        current = self._schedules.get(schedule.patient_id)
        if current is not None:
            schedule = schedule.model_copy(update={"version": current.version + 1})

        # Planning Agent chỉ sinh khung giờ. ID cữ được gắn bằng code xác định
        # để client có thể ghi action idempotent mà không cho agent tự tạo ID.
        slots = []
        for slot_index, slot in enumerate(schedule.slots, start=1):
            doses = [
                dose.model_copy(
                    update={"id": dose.id or f"{schedule.id}-{slot_index:02d}-{dose_index:02d}"},
                )
                for dose_index, dose in enumerate(slot.doses, start=1)
            ]
            slots.append(slot.model_copy(update={"doses": doses}))
        schedule = schedule.model_copy(update={"slots": slots})
        self._schedules[schedule.patient_id] = schedule
        return schedule

    def get_schedule(self, patient_id: str) -> MedicationSchedule | None:
        return self._schedules.get(patient_id)

    def record_dose_action(
        self,
        dose_id: str,
        action: DoseAction,
        note: str,
        idempotency_key: str,
    ) -> DoseActionRecord | None:
        replay = self._dose_action_keys.get(idempotency_key)
        if replay is not None:
            if replay.dose_id != dose_id or replay.status != action:
                raise ValueError("Idempotency-Key đã được dùng cho một hành động khác.")
            return replay

        target: tuple[str, MedicationSchedule, int, int] | None = None
        for patient_id, schedule in self._schedules.items():
            for slot_index, slot in enumerate(schedule.slots):
                for dose_index, dose in enumerate(slot.doses):
                    if dose.id == dose_id:
                        target = (patient_id, schedule, slot_index, dose_index)
                        break
                if target is not None:
                    break
            if target is not None:
                break

        if target is None:
            return None

        patient_id, schedule, slot_index, dose_index = target
        dose = schedule.slots[slot_index].doses[dose_index]
        if dose.status in (DoseStatus.TAKEN, DoseStatus.LATE, DoseStatus.SKIPPED, DoseStatus.MISSED):
            raise ValueError(f"Cữ thuốc {dose_id} đã được ghi nhận là {dose.status.value}.")

        next_status = DoseStatus(action.value)
        slots = list(schedule.slots)
        doses = list(slots[slot_index].doses)
        doses[dose_index] = dose.model_copy(update={"status": next_status})
        slots[slot_index] = slots[slot_index].model_copy(update={"doses": doses})
        self._schedules[patient_id] = schedule.model_copy(update={"slots": slots})

        recorded_at = now_iso()
        record = DoseActionRecord(
            id=f"ACT-{next(self._action_seq):05d}",
            dose_id=dose_id,
            patient_id=patient_id,
            status=action,
            note=note,
            recorded_at=recorded_at,
        )
        self._dose_actions[dose_id] = record
        self._dose_action_keys[idempotency_key] = record

        action_label = {
            DoseAction.TAKEN: "TAKEN",
            DoseAction.LATE: "LATE",
            DoseAction.SKIPPED: "SKIPPED",
        }[action]
        self._logs.setdefault(patient_id, []).insert(
            0,
            AdherenceLog(
                at=datetime.now(UTC).strftime("%H:%M"),
                status=next_status,
                message=f"{dose.drug_name} — {action_label}" + (f" · {note}" if note else ""),
            ),
        )

        patient = self._patients[patient_id]
        miss_count = patient.consecutive_miss + 1 if action is DoseAction.SKIPPED else 0
        tone = "crit" if action is DoseAction.SKIPPED else "warn" if action is DoseAction.LATE else "ok"
        self._patients[patient_id] = patient.model_copy(
            update={
                "consecutive_miss": miss_count,
                "last_event": LastEvent(
                    text=f"{dose.drug_name} — {action_label}",
                    tone=tone,
                    at="vừa xong",
                ),
            }
        )
        return record

    def adherence_summary(self, patient_id: str) -> AdherenceSummary | None:
        patient = self._patients.get(patient_id)
        if patient is None:
            return None
        schedule = self._schedules.get(patient_id)
        statuses = [dose.status for slot in schedule.slots for dose in slot.doses] if schedule else []
        return AdherenceSummary(
            patient_id=patient_id,
            adherence_rate=patient.adherence_rate,
            taken=statuses.count(DoseStatus.TAKEN),
            late=statuses.count(DoseStatus.LATE),
            skipped=statuses.count(DoseStatus.SKIPPED),
            missed=statuses.count(DoseStatus.MISSED),
            pending=statuses.count(DoseStatus.PENDING) + statuses.count(DoseStatus.SENT),
        )

    def save_health_survey(self, patient_id: str, payload: HealthSurveyCreate) -> HealthSurvey:
        survey = HealthSurvey(
            id=f"SUR-{next(self._survey_seq):05d}",
            patient_id=patient_id,
            submitted_at=now_iso(),
            **payload.model_dump(),
        )
        self._health_surveys[survey.id] = survey
        symptom_text = ", ".join(payload.symptoms) if payload.symptoms else "không triệu chứng"
        self._logs.setdefault(patient_id, []).insert(
            0,
            AdherenceLog(
                at=datetime.now(UTC).strftime("%H:%M"),
                message=f"Khảo sát sức khỏe: {symptom_text} ({payload.severity.value})",
            ),
        )

        if payload.severity is SymptomSeverity.SEVERE:
            alert = self._new_alert(
                patient_id=patient_id,
                kind=AlertKind.SEVERE_SYMPTOM,
                title="Triệu chứng mức SEVERE",
                detail=f"Bệnh nhân khai báo: {symptom_text}. Cần bác sĩ đánh giá.",
            )
            patient = self._patients[patient_id]
            self._patients[patient_id] = patient.model_copy(
                update={
                    "status": PatientStatus.RED_ALERT,
                    "symptom": symptom_text,
                    "last_event": LastEvent(text=alert.title, tone="crit", at="vừa xong"),
                }
            )
        return survey

    def create_sos(self, patient_id: str, payload: SosCreate, idempotency_key: str) -> SosEvent:
        replay = self._sos_keys.get(idempotency_key)
        if replay is not None:
            if replay.patient_id != patient_id:
                raise ValueError("Idempotency-Key đã được dùng cho một yêu cầu SOS khác.")
            return replay

        detail = payload.note.strip() or "Bệnh nhân kích hoạt SOS từ ứng dụng."
        if payload.share_location:
            detail += " Bệnh nhân đồng ý chia sẻ vị trí với kênh cứu trợ."
        alert = self._new_alert(
            patient_id=patient_id,
            kind=AlertKind.SOS,
            title="SOS từ ứng dụng bệnh nhân",
            detail=detail,
        )
        event = SosEvent(
            id=f"SOS-{next(self._sos_seq):05d}",
            patient_id=patient_id,
            note=payload.note,
            share_location=payload.share_location,
            created_at=now_iso(),
            alert_id=alert.id,
        )
        self._sos_events[event.id] = event
        self._sos_keys[idempotency_key] = event
        self._logs.setdefault(patient_id, []).insert(
            0,
            AdherenceLog(at=datetime.now(UTC).strftime("%H:%M"), message="SOS từ ứng dụng — Red Alert đã mở"),
        )
        patient = self._patients[patient_id]
        self._patients[patient_id] = patient.model_copy(
            update={
                "status": PatientStatus.SOS,
                "last_event": LastEvent(text="Nhấn SOS từ ứng dụng", tone="crit", at="vừa xong"),
            }
        )
        return event

    def _new_alert(self, patient_id: str, kind: AlertKind, title: str, detail: str) -> Alert:
        alert = Alert(
            id=f"AL-{next(self._alert_seq)}",
            kind=kind,
            patient_id=patient_id,
            title=title,
            detail=detail,
            opened_at=datetime.now(UTC).strftime("%H:%M"),
            state=AlertState.OPEN,
            channels=[
                AlertChannel(name="Portal bác sĩ", status="DELIVERED"),
                AlertChannel(name="SMS người thân", status="SENT"),
            ],
            dispatch_ms=800,
        )
        self._alerts[alert.id] = alert
        return alert

    # ---------- alerts ----------
    def list_alerts(self, state: AlertState | None = None) -> list[Alert]:
        alerts = list(self._alerts.values())
        if state is not None:
            alerts = [a for a in alerts if a.state == state]
        return alerts

    def get_alert(self, alert_id: str) -> Alert | None:
        return self._alerts.get(alert_id)

    def set_alert_state(self, alert_id: str, state: AlertState) -> Alert | None:
        alert = self._alerts.get(alert_id)
        if alert is None:
            return None
        updated = alert.model_copy(update={"state": state})
        self._alerts[alert_id] = updated
        return updated

    # ---------- catalog ----------
    def search_drugs(self, query: str = "") -> list[DrugCatalogEntry]:
        needle = query.strip().lower()
        return [
            DrugCatalogEntry(drug_id=f"drug-{index:03d}", brand_name=name)
            for index, name in enumerate(DRUG_CATALOG)
            if needle in name.lower()
        ]


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


store = Store()
