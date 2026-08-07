from fastapi import APIRouter, HTTPException, Query

from src.agents.graph import agent
from src.agents.planning_graph import run_planning
from src.config import get_settings
from src.models.clinical import (
    AdherenceLog,
    Alert,
    AlertResolveRequest,
    AlertState,
    DashboardSummary,
    DrugCatalogEntry,
    GenerateScheduleRequest,
    MedicationSchedule,
    Patient,
    PatientDetail,
    PatientRoutine,
    Prescription,
    PrescriptionCreate,
    PrescriptionItem,
    PrescriptionStatus,
)
from src.models.schemas import ChatRequest, ChatResponse
from src.services.prescription_validator import validate_items
from src.services.store import now_iso, store

router = APIRouter()

# Chỉ số demo cố định — chỗ này sẽ thay bằng aggregate thật khi có DB.
_RESPONSE_MINUTES = 17
_DOSES_DUE_TODAY = 96
_DOSES_MISSED_TODAY = 11
_RED_ALERT_PRECISION = 92


def _get_patient_or_404(patient_id: str) -> Patient:
    patient = store.get_patient(patient_id)
    if patient is None:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy bệnh nhân {patient_id}")
    return patient


# --------------------------------------------------------------------------
# Agent boilerplate (giữ nguyên từ template)
# --------------------------------------------------------------------------
@router.post("/chat", response_model=ChatResponse, operation_id="chat")
async def chat(request: ChatRequest) -> ChatResponse:
    """Chat với AI agent."""
    try:
        result = await agent.ainvoke({"query": request.message})
        return ChatResponse(
            response=result.get("response", ""),
            analysis=result.get("analysis", ""),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status", operation_id="agentStatus")
async def agent_status():
    """Kiểm tra trạng thái agent."""
    return {"status": "ready", "agent": "LangGraph Agent v1.0"}


# --------------------------------------------------------------------------
# Dashboard (FR-1.2)
# --------------------------------------------------------------------------
@router.get("/dashboard/summary", response_model=DashboardSummary, operation_id="getDashboardSummary")
async def dashboard_summary() -> DashboardSummary:
    patients = store.list_patients()
    live_alerts = [a for a in store.list_alerts() if a.state in (AlertState.OPEN, AlertState.ACKNOWLEDGED)]
    adherence_avg = round(sum(p.adherence_rate for p in patients) / len(patients)) if patients else 0
    return DashboardSummary(
        patients_total=len(patients),
        adherence_avg=adherence_avg,
        response_minutes=_RESPONSE_MINUTES,
        open_alerts=len(live_alerts),
        doses_missed_today=_DOSES_MISSED_TODAY,
        doses_due_today=_DOSES_DUE_TODAY,
        red_alert_precision=_RED_ALERT_PRECISION,
    )


@router.get("/dashboard/patients", response_model=list[Patient], operation_id="listDashboardPatients")
async def list_dashboard_patients() -> list[Patient]:
    return store.list_patients()


@router.get("/dashboard/patients/{patient_id}", response_model=PatientDetail, operation_id="getDashboardPatient")
async def get_dashboard_patient(patient_id: str) -> PatientDetail:
    detail = store.get_patient_detail(patient_id)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy bệnh nhân {patient_id}")
    return detail


@router.get(
    "/patients/{patient_id}/adherence/logs", response_model=list[AdherenceLog], operation_id="listAdherenceLogs"
)
async def list_adherence_logs(patient_id: str) -> list[AdherenceLog]:
    _get_patient_or_404(patient_id)
    return store.logs_for(patient_id)


# --------------------------------------------------------------------------
# Lịch sinh hoạt bệnh nhân
# --------------------------------------------------------------------------
@router.get("/patients/{patient_id}/routine", response_model=PatientRoutine, operation_id="getPatientRoutine")
async def get_patient_routine(patient_id: str) -> PatientRoutine:
    return _get_patient_or_404(patient_id).routine


@router.put("/patients/{patient_id}/routine", response_model=PatientRoutine, operation_id="updatePatientRoutine")
async def update_patient_routine(patient_id: str, routine: PatientRoutine) -> PatientRoutine:
    _get_patient_or_404(patient_id)
    updated = store.update_routine(patient_id, routine)
    assert updated is not None
    return updated.routine


# --------------------------------------------------------------------------
# Đơn thuốc (FR-1.1) — HITL bắt buộc
# --------------------------------------------------------------------------
@router.post(
    "/patients/{patient_id}/prescriptions",
    response_model=Prescription,
    status_code=201,
    operation_id="createPrescription",
)
async def create_prescription(patient_id: str, payload: PrescriptionCreate) -> Prescription:
    """Tạo đơn nháp. Đơn DRAFT không sinh lịch nhắc."""
    _get_patient_or_404(patient_id)
    settings = get_settings()

    prescription = Prescription(
        id=store.next_prescription_id(),
        patient_id=patient_id,
        doctor_id=settings.doctor_id,
        status=PrescriptionStatus.DRAFT,
        created_at=now_iso(),
        items=[PrescriptionItem(seq=index + 1, **item.model_dump()) for index, item in enumerate(payload.items)],
    )
    return store.save_prescription(prescription)


@router.get(
    "/patients/{patient_id}/prescriptions",
    response_model=list[Prescription],
    operation_id="listPrescriptions",
)
async def list_prescriptions(patient_id: str) -> list[Prescription]:
    _get_patient_or_404(patient_id)
    return store.list_prescriptions(patient_id)


@router.get("/prescriptions/{prescription_id}", response_model=Prescription, operation_id="getPrescription")
async def get_prescription(prescription_id: str) -> Prescription:
    prescription = store.get_prescription(prescription_id)
    if prescription is None:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy đơn {prescription_id}")
    return prescription


@router.post(
    "/prescriptions/{prescription_id}/approve", response_model=Prescription, operation_id="approvePrescription"
)
async def approve_prescription(prescription_id: str) -> Prescription:
    """Bác sĩ duyệt đơn. Validator bằng code là cổng bắt buộc trước khi persist."""
    prescription = store.get_prescription(prescription_id)
    if prescription is None:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy đơn {prescription_id}")
    if prescription.status is not PrescriptionStatus.DRAFT:
        raise HTTPException(
            status_code=409,
            detail=f"Đơn {prescription_id} đang ở trạng thái {prescription.status.value}, không duyệt lại được.",
        )

    report = validate_items(prescription.items)
    if not report.ok:
        raise HTTPException(status_code=422, detail=[issue.model_dump() for issue in report.issues])

    approved = prescription.model_copy(
        update={"status": PrescriptionStatus.APPROVED, "approved_at": now_iso()},
    )
    return store.save_prescription(approved)


@router.post("/prescriptions/{prescription_id}/cancel", response_model=Prescription, operation_id="cancelPrescription")
async def cancel_prescription(prescription_id: str) -> Prescription:
    prescription = store.get_prescription(prescription_id)
    if prescription is None:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy đơn {prescription_id}")
    cancelled = prescription.model_copy(update={"status": PrescriptionStatus.CANCELLED})
    return store.save_prescription(cancelled)


# --------------------------------------------------------------------------
# Lịch nhắc (FR-2.1)
# --------------------------------------------------------------------------
@router.post(
    "/patients/{patient_id}/schedules/generate",
    response_model=MedicationSchedule,
    operation_id="generateSchedule",
)
async def generate_schedule(patient_id: str, payload: GenerateScheduleRequest) -> MedicationSchedule:
    """Kích hoạt Planning Agent trên một đơn đã duyệt."""
    patient = _get_patient_or_404(patient_id)
    prescription = store.get_prescription(payload.prescription_id)

    if prescription is None:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy đơn {payload.prescription_id}")
    if prescription.patient_id != patient_id:
        raise HTTPException(status_code=403, detail="Đơn thuốc không thuộc về bệnh nhân này.")
    if prescription.status is not PrescriptionStatus.APPROVED:
        raise HTTPException(
            status_code=409,
            detail=f"Đơn {prescription.id} chưa được duyệt — không sinh lịch nhắc.",
        )

    schedule = await run_planning(prescription, patient.routine, store.next_schedule_id())
    return store.save_schedule(schedule)


@router.get("/patients/{patient_id}/schedules", response_model=MedicationSchedule, operation_id="getSchedule")
async def get_schedule(patient_id: str) -> MedicationSchedule:
    _get_patient_or_404(patient_id)
    schedule = store.get_schedule(patient_id)
    if schedule is None:
        raise HTTPException(status_code=404, detail="Bệnh nhân chưa có lịch nhắc nào.")
    return schedule


# --------------------------------------------------------------------------
# Cảnh báo (FR-4.2)
# --------------------------------------------------------------------------
@router.get("/alerts", response_model=list[Alert], operation_id="listAlerts")
async def list_alerts(state: AlertState | None = Query(default=None)) -> list[Alert]:
    return store.list_alerts(state)


@router.post("/alerts/{alert_id}/acknowledge", response_model=Alert, operation_id="acknowledgeAlert")
async def acknowledge_alert(alert_id: str) -> Alert:
    alert = store.get_alert(alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy cảnh báo {alert_id}")
    if alert.state is not AlertState.OPEN:
        raise HTTPException(status_code=409, detail=f"Cảnh báo đang ở trạng thái {alert.state.value}.")
    updated = store.set_alert_state(alert_id, AlertState.ACKNOWLEDGED)
    assert updated is not None
    return updated


@router.post("/alerts/{alert_id}/resolve", response_model=Alert, operation_id="resolveAlert")
async def resolve_alert(alert_id: str, payload: AlertResolveRequest) -> Alert:
    """Đóng cảnh báo. Chỉ bác sĩ đã tiếp nhận mới đóng được — hệ thống không tự đóng."""
    alert = store.get_alert(alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy cảnh báo {alert_id}")
    if alert.state not in (AlertState.ACKNOWLEDGED, AlertState.ESCALATING):
        raise HTTPException(
            status_code=409,
            detail="Phải tiếp nhận cảnh báo trước khi đóng.",
        )
    target = AlertState.CLOSED_FALSE_POSITIVE if payload.false_positive else AlertState.RESOLVED
    updated = store.set_alert_state(alert_id, target)
    assert updated is not None
    return updated


# --------------------------------------------------------------------------
# Danh mục thuốc (autocomplete cho form kê đơn)
# --------------------------------------------------------------------------
@router.get("/drugs", response_model=list[DrugCatalogEntry], operation_id="searchDrugs")
async def search_drugs(q: str = Query(default="", max_length=100)) -> list[DrugCatalogEntry]:
    return store.search_drugs(q)
