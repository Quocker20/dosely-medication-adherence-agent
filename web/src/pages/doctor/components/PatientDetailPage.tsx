import { useCallback, useEffect, useMemo, useState } from "react";

import { ApiError, api, waitForAgentRun } from "../../../api";
import type {
  ActiveSchedule,
  AdherenceLog,
  AlertDetail,
  DashboardPatientDetail,
  HealthSurveyFullDetail,
  PatientDetail,
  PatientRoutine,
  PrescriptionDetail,
} from "../../../types";
import {
  adherenceTone,
  alertSeverityView,
  alertStatusView,
  alertTriggerLabel,
  formatDate,
  formatDateTime,
  formatDoseValue,
  formatTime,
  isoDate,
  patientDisplayName,
} from "../../../utils/labels";

type DetailTab = "overview" | "medications" | "health" | "routine";

const TABS: Array<{ id: DetailTab; label: string }> = [
  { id: "overview", label: "Tổng quan" },
  { id: "medications", label: "Thuốc đang điều trị" },
  { id: "health", label: "Sức khỏe & tuân thủ" },
  { id: "routine", label: "Lịch sinh hoạt & nhắc thuốc" },
];

const ROUTINE_FIELDS: Array<[string, keyof PatientRoutine]> = [
  ["Thức dậy", "wake_time"],
  ["Ăn sáng", "breakfast_time"],
  ["Ăn trưa", "lunch_time"],
  ["Ăn tối", "dinner_time"],
  ["Đi ngủ", "sleep_time"],
];

interface Props {
  patientId: string;
  accessToken: string;
  onBack: () => void;
  onPrescribe: (phone: string) => void;
  onToast: (message: string) => void;
}

function dateDaysAgo(days: number): string {
  const date = new Date();
  date.setDate(date.getDate() - days);
  return isoDate(date);
}

function ageOf(dob: string | null): string {
  if (!dob) return "Chưa khai báo";
  const date = new Date(dob);
  if (Number.isNaN(date.getTime())) return "Chưa khai báo";
  const now = new Date();
  const years = now.getFullYear() - date.getFullYear();
  const beforeBirthday = now.getMonth() < date.getMonth() || (now.getMonth() === date.getMonth() && now.getDate() < date.getDate());
  return `${years - Number(beforeBirthday)} tuổi`;
}

function shortTime(value: string | null): string {
  return value ? value.slice(0, 5) : "—";
}

function EmptyState({ children }: { children: React.ReactNode }) {
  return <p className="detail-empty">{children}</p>;
}

export default function PatientDetailPage({ patientId, accessToken, onBack, onPrescribe, onToast }: Props) {
  const [tab, setTab] = useState<DetailTab>("overview");
  const [profile, setProfile] = useState<PatientDetail | null>(null);
  const [detail, setDetail] = useState<DashboardPatientDetail | null>(null);
  const [routine, setRoutine] = useState<PatientRoutine | null>(null);
  const [schedule, setSchedule] = useState<ActiveSchedule | null>(null);
  const [prescriptions, setPrescriptions] = useState<PrescriptionDetail[]>([]);
  const [logs, setLogs] = useState<AdherenceLog[]>([]);
  const [alerts, setAlerts] = useState<AlertDetail[]>([]);
  const [surveys, setSurveys] = useState<HealthSurveyFullDetail[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [scheduleBusy, setScheduleBusy] = useState(false);

  const refresh = useCallback(async () => {
    const from = dateDaysAgo(29);
    const to = isoDate(new Date());
    const [profileResult, detailResult, prescriptionsResult, logsResult, alertsResult, surveysResult] = await Promise.all([
      api.patient(patientId),
      api.dashboardPatientDetail(patientId),
      api.patientPrescriptions(patientId, { size: 50 }),
      api.adherenceLogs(patientId, from, to, 20),
      api.alerts({ patientId, size: 20 }),
      api.patientHealthSurveys(patientId, { from, to, size: 8 }),
    ]);
    // A patient who has not completed onboarding may legitimately have no
    // routine yet; that must not make the clinical detail page unavailable.
    const [routineResult, scheduleResult] = await Promise.allSettled([
      api.patientRoutine(patientId),
      api.schedule(patientId, to),
    ]);
    const surveyDetails = await Promise.all(
      surveysResult.content.map((survey) => api.healthSurveyDetail(survey.id)),
    );
    setProfile(profileResult);
    setDetail(detailResult);
    setRoutine(routineResult.status === "fulfilled" ? routineResult.value : null);
    setSchedule(scheduleResult.status === "fulfilled" ? scheduleResult.value : null);
    setPrescriptions(prescriptionsResult.content);
    setLogs(logsResult.content);
    setAlerts(alertsResult.content);
    setSurveys(surveyDetails);
  }, [patientId]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    refresh()
      .catch((cause: unknown) => {
        if (!cancelled) setError(cause instanceof ApiError ? cause.message : "Không tải được hồ sơ bệnh nhân.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
  }, [refresh]);

  useEffect(() => {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const wsHost = import.meta.env.VITE_WS_HOST || window.location.host;
    const socket = new WebSocket(`${protocol}//${wsHost}/ws/dashboard?token=${encodeURIComponent(accessToken)}`);
    socket.onopen = () => { refresh().catch(() => {}); };
    socket.onmessage = (event) => {
      try {
        const frame = JSON.parse(event.data) as { data?: { patient_id?: string } };
        if (frame.data?.patient_id === patientId) refresh().catch(() => {});
      } catch { /* Invalid realtime frame is safely ignored. */ }
    };
    return () => socket.close();
  }, [accessToken, patientId, refresh]);

  const activePrescriptions = useMemo(
    () => prescriptions.filter((prescription) => prescription.status === "APPROVED"),
    [prescriptions],
  );

  async function generateSchedule() {
    setScheduleBusy(true);
    try {
      const run = await waitForAgentRun((await api.generateSchedule(patientId, "Bác sĩ yêu cầu tính lại lịch từ hồ sơ bệnh nhân")).agent_run_id);
      if (run.status === "COMPLETED") {
        setSchedule(await api.schedule(patientId, isoDate(new Date())));
        onToast(`Đã tính lại lịch nhắc · ${run.generated_dose_count ?? 0} cữ`);
      } else {
        onToast(`Agent chưa hoàn tất lịch · ${run.status}`);
      }
    } catch (cause) {
      onToast(cause instanceof ApiError ? cause.message : "Không tính được lịch nhắc.");
    } finally {
      setScheduleBusy(false);
    }
  }

  if (loading) return <section className="view"><p className="detail-empty">Đang tải hồ sơ bệnh nhân…</p></section>;
  if (error || !profile || !detail) return <section className="view"><div className="errors"><b>Không mở được hồ sơ bệnh nhân</b><p>{error ?? "Dữ liệu không đầy đủ."}</p><button className="btn" onClick={onBack}>Quay lại danh sách</button></div></section>;

  const summary = detail.adherence_summary;
  const openAlerts = alerts.filter((alert) => alert.status !== "RESOLVED").length;
  const adherenceClass = adherenceTone(summary.adherence_rate);

  return (
    <section className="view patient-detail-page">
      <button className="detail-back" onClick={onBack}>← Danh sách bệnh nhân</button>
      <header className="detail-hero card">
        <div className="detail-avatar">{patientDisplayName(profile.name).slice(0, 1)}</div>
        <div className="detail-identity">
          <div className="eyebrow">Hồ sơ điều trị</div>
          <h1>{patientDisplayName(profile.name)}</h1>
          <p>{profile.phone} · {ageOf(profile.dob)} · {profile.sex === "MALE" ? "Nam" : profile.sex === "FEMALE" ? "Nữ" : "Chưa khai báo giới tính"}</p>
        </div>
        <div className="detail-actions">
          <button className="btn primary" onClick={() => onPrescribe(profile.phone)}>Kê đơn mới</button>
          <button className="btn" disabled={scheduleBusy} onClick={generateSchedule}>{scheduleBusy ? "Đang tính…" : "Tính lại lịch nhắc"}</button>
        </div>
      </header>

      <div className="detail-tabs" role="tablist" aria-label="Nội dung hồ sơ bệnh nhân">
        {TABS.map((item) => <button key={item.id} role="tab" aria-selected={tab === item.id} className={tab === item.id ? "active" : ""} onClick={() => setTab(item.id)}>{item.label}</button>)}
      </div>

      {tab === "overview" && <>
        <div className="detail-kpis">
          <article className="card"><span>Tuân thủ {summary.window_days} ngày</span><strong className={adherenceClass}>{Math.round(summary.adherence_rate)}%</strong><small>{summary.taken_doses}/{summary.total_doses} cữ đã uống</small></article>
          <article className="card"><span>Cảnh báo cần xử lý</span><strong className={openAlerts ? "crit" : "ok"}>{openAlerts}</strong><small>{openAlerts ? "Cần bác sĩ theo dõi" : "Không có cảnh báo mở"}</small></article>
          <article className="card"><span>Đơn đang hiệu lực</span><strong>{detail.active_prescriptions_count}</strong><small>Chỉ đơn APPROVED được lập lịch</small></article>
          <article className="card"><span>Khảo sát gần nhất</span><strong>{surveys[0] ? formatDate(surveys[0].survey_date) : "—"}</strong><small>{surveys[0]?.status ?? "Chưa có khảo sát"}</small></article>
        </div>
        <div className="detail-two-col">
          <article className="card"><div className="card-head"><h2>Tóm tắt tuân thủ</h2></div><div className="card-body detail-stat-list"><span>Đã uống <b>{summary.taken_doses}</b></span><span>Bỏ qua <b className="warn">{summary.skipped_doses}</b></span><span>Không phản hồi <b className="crit">{summary.missed_doses}</b></span></div></article>
          <article className="card"><div className="card-head"><h2>Cảnh báo gần đây</h2></div><div className="card-body detail-list">{alerts.slice(0, 4).map((alert) => <AlertRow alert={alert} key={alert.id} />)}{alerts.length === 0 && <EmptyState>Không có cảnh báo nào gần đây.</EmptyState>}</div></article>
        </div>
      </>}

      {tab === "medications" && <article className="card"><div className="card-head"><div><h2>Đơn thuốc đã duyệt</h2><p className="detail-subtitle">Thông tin chỉ đọc. Mọi thay đổi phác đồ phải qua đơn mới và bác sĩ duyệt.</p></div></div><div className="card-body detail-list">{activePrescriptions.map((prescription) => <div className="prescription-card" key={prescription.id}><div><b>Đơn #{prescription.id.slice(0, 8)}</b><span className="pill ok">APPROVED</span><small>Hiệu lực từ {formatDate(prescription.approved_at ?? prescription.created_at)}</small></div>{prescription.items.map((item) => <div className="medication-detail" key={item.id}><strong>{item.display_name}</strong><span>{[item.morning_dose && `Sáng ${item.morning_dose} ${item.dose_unit}`, item.noon_dose && `Trưa ${item.noon_dose} ${item.dose_unit}`, item.evening_dose && `Tối ${item.evening_dose} ${item.dose_unit}`, item.bedtime_dose && `Trước ngủ ${item.bedtime_dose} ${item.dose_unit}`].filter(Boolean).join(" · ") || "Liều chưa khai báo"}</span><small>{item.route}{item.meal_relation ? ` · ${item.meal_relation}` : ""}{item.instructions ? ` · ${item.instructions}` : ""}</small></div>)}</div>)}{activePrescriptions.length === 0 && <EmptyState>Chưa có đơn thuốc APPROVED.</EmptyState>}</div></article>}

      {tab === "health" && <div className="detail-two-col"><article className="card"><div className="card-head"><h2>Nhật ký tuân thủ</h2></div><div className="card-body detail-list">{logs.map((log) => <div className="detail-row" key={log.id}><b className={log.action === "TAKEN" ? "ok" : "crit"}>{log.action}</b><span>{formatDateTime(log.performed_at)}</span></div>)}{logs.length === 0 && <EmptyState>Chưa có nhật ký trong 30 ngày gần nhất.</EmptyState>}</div></article><article className="card"><div className="card-head"><h2>Khảo sát & triệu chứng</h2></div><div className="card-body detail-list">{surveys.map((survey) => <div className="survey-detail" key={survey.id}><b>{formatDate(survey.survey_date)} · {survey.status}</b>{survey.symptoms.map((symptom) => <span key={symptom.id}>{symptom.symptom_code} · {symptom.severity}{symptom.description ? ` · ${symptom.description}` : ""}</span>)}{survey.symptoms.length === 0 && <small>Không ghi nhận triệu chứng.</small>}</div>)}{surveys.length === 0 && <EmptyState>Chưa có khảo sát sức khỏe.</EmptyState>}</div></article></div>}

      {tab === "routine" && <div className="detail-two-col"><article className="card"><div className="card-head"><div><h2>Lịch sinh hoạt</h2><p className="detail-subtitle">Bệnh nhân tự cập nhật trên web hoặc ứng dụng; đây là đầu vào của Planning Agent.</p></div></div><div className="card-body routine-readonly">{ROUTINE_FIELDS.map(([label, key]) => <span key={key}><b>{label}</b><time>{shortTime(routine?.[key] ?? null)}</time></span>)}{!routine && <EmptyState>Bệnh nhân chưa khai báo lịch sinh hoạt.</EmptyState>}</div></article><article className="card"><div className="card-head"><h2>Lịch uống hôm nay</h2></div><div className="card-body detail-list">{schedule?.doses.map((dose) => <div className="detail-row" key={dose.scheduled_dose_id}><time>{formatTime(dose.current_scheduled_at)}</time><span><b>{dose.medication_name}</b><small>{formatDoseValue(dose.dose_value)} {dose.dose_unit ?? ""} · {dose.status}</small></span></div>)}{!schedule?.doses.length && <EmptyState>Chưa có cữ thuốc hôm nay.</EmptyState>}</div></article></div>}

      <p className="detail-safety-note">Planning Agent chỉ có thể tính lại giờ nhắc theo đơn APPROVED và lịch sinh hoạt. Hệ thống không tự thay đổi liều, số cữ, đường dùng hoặc thời gian điều trị.</p>
    </section>
  );
}

function AlertRow({ alert }: { alert: AlertDetail }) {
  const status = alertStatusView(alert.status);
  const severity = alertSeverityView(alert.severity);
  return <div className="detail-row"><span><b>{alertTriggerLabel(alert.triggered_by_type)}</b><small>{formatDateTime(alert.created_at)}</small></span><span className={`pill ${severity.tone}`}>{severity.label} · {status.label}</span></div>;
}
