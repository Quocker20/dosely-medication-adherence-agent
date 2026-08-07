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
    Alert,
    AlertChannel,
    AlertKind,
    AlertState,
    DoseStatus,
    DrugCatalogEntry,
    LastEvent,
    MedicationSchedule,
    Patient,
    PatientDetail,
    PatientRoutine,
    PatientStatus,
    Prescription,
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


class Store:
    """Repository in-memory. Mọi thay đổi trạng thái đi qua đây."""

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self._patients: dict[str, Patient] = {p.id: p for p in _seed_patients()}
        self._logs = _seed_logs()
        self._week = _seed_week()
        self._alerts: dict[str, Alert] = {a.id: a for a in _seed_alerts()}
        self._prescriptions: dict[str, Prescription] = {}
        self._schedules: dict[str, MedicationSchedule] = {}
        self._rx_seq = itertools.count(2401)
        self._schedule_seq = itertools.count(9101)

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
        self._schedules[schedule.patient_id] = schedule
        return schedule

    def get_schedule(self, patient_id: str) -> MedicationSchedule | None:
        return self._schedules.get(patient_id)

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
