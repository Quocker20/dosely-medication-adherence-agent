import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { ApiError, api } from "../../api";
import { setSession, type Session } from "../../session";
import type { ActiveSchedule, AdherenceSummary, ScheduledDoseRow } from "../../types";

type Tab = "dashboard" | "schedule" | "assistant" | "survey" | "sos";
type DoseAction = (dose: ScheduledDoseRow, type: "TAKEN" | "SNOOZE" | "SKIPPED") => Promise<void>;
type IconName = "home" | "calendar" | "assistant" | "send" | "mic" | "heart" | "alert" | "pill" | "logout" | "bell" | "check" | "clock" | "shield";
interface ChatMessage { id: string; role: "user" | "assistant"; content: string; time: string }

const symptoms = ["Không có", "Chóng mặt", "Buồn nôn", "Đau đầu", "Mệt mỏi"];
const symptomCodes: Record<string, string> = { "Không có": "NONE", "Chóng mặt": "DIZZINESS", "Buồn nôn": "NAUSEA", "Đau đầu": "HEADACHE", "Mệt mỏi": "FATIGUE" };
const navItems: Array<{ id: Tab; label: string; description: string; icon: IconName }> = [
  { id: "dashboard", label: "Tổng quan", description: "Sức khỏe hôm nay", icon: "home" },
  { id: "schedule", label: "Lịch uống thuốc", description: "Các cữ trong ngày", icon: "calendar" },
  { id: "assistant", label: "Trợ lý AI", description: "Hỏi về thuốc & lịch", icon: "assistant" },
  { id: "survey", label: "Khảo sát sức khỏe", description: "Cập nhật cho bác sĩ", icon: "heart" },
  { id: "sos", label: "Hỗ trợ khẩn cấp", description: "Gửi cảnh báo SOS", icon: "alert" },
];

function Icon({ name, size = 20 }: { name: IconName; size?: number }) {
  const paths: Record<IconName, React.ReactNode> = {
    home: <><path d="m3 10 9-7 9 7"/><path d="M5 9v11h14V9"/><path d="M9 20v-6h6v6"/></>,
    calendar: <><rect x="3" y="5" width="18" height="16" rx="2"/><path d="M16 3v4M8 3v4M3 10h18"/></>,
    assistant: <><rect x="4" y="6" width="16" height="13" rx="4"/><path d="M9 11h.01M15 11h.01M9 15h6M12 3v3"/></>,
    send: <><path d="m22 2-7 20-4-9-9-4Z"/><path d="M22 2 11 13"/></>,
    mic: <><rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5 11a7 7 0 0 0 14 0M12 18v3M8 21h8"/></>,
    heart: <path d="M20.8 4.6a5.5 5.5 0 0 0-7.8 0L12 5.7l-1.1-1.1a5.5 5.5 0 0 0-7.8 7.8l1.1 1.1L12 21l7.8-7.5 1.1-1.1a5.5 5.5 0 0 0-.1-7.8Z"/>,
    alert: <><path d="M10.3 2.9 1.8 17.1A2 2 0 0 0 3.5 20h17a2 2 0 0 0 1.7-2.9L13.7 2.9a2 2 0 0 0-3.4 0Z"/><path d="M12 9v4M12 17h.01"/></>,
    pill: <><path d="m10.5 20.5-7-7a5 5 0 0 1 7-7l7 7a5 5 0 0 1-7 7Z"/><path d="m8.5 8.5 7 7"/></>,
    logout: <><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><path d="m16 17 5-5-5-5M21 12H9"/></>,
    bell: <><path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9"/><path d="M10 21h4"/></>,
    check: <path d="m5 12 4 4L19 6"/>, clock: <><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></>,
    shield: <><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10Z"/><path d="m9 12 2 2 4-4"/></>,
  };
  return <svg viewBox="0 0 24 24" width={size} height={size} fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name]}</svg>;
}

const isoDate = (date: Date) => date.toLocaleDateString("en-CA", { timeZone: "Asia/Ho_Chi_Minh" });
function prettyTime(value: string) { const parsed = new Date(value); return Number.isNaN(parsed.valueOf()) ? value.slice(0, 5) : parsed.toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" }); }
function doseStatus(status: string) {
  const value = status.toUpperCase();
  if (value === "TAKEN") return ["Đã uống", "taken"] as const;
  if (value === "SKIPPED" || value === "MISSED") return [value === "SKIPPED" ? "Đã bỏ qua" : "Đã lỡ", "missed"] as const;
  if (value === "SNOOZED") return ["Đã hoãn", "late"] as const;
  return ["Sắp tới", "upcoming"] as const;
}
function isDoseLocked(dose: ScheduledDoseRow) {
  return dose.status.toUpperCase() === "PENDING" && new Date(dose.current_scheduled_at).getTime() > Date.now();
}
function chatStorageKey(patientId: string) { return `remindrx.patient-chat.${patientId}`; }
function welcomeChatMessages(): ChatMessage[] {
  return [{ id: "welcome", role: "assistant", content: "Chào bạn! Tôi là trợ lý RemindRx. Tôi có thể giúp bạn tra cứu lịch uống thuốc, giải thích thông tin thuốc từ nguồn tham khảo và ghi nhận vấn đề cần bác sĩ xem xét.", time: "Bây giờ" }];
}
function isChatMessage(value: unknown): value is ChatMessage {
  if (!value || typeof value !== "object") return false;
  const message = value as Record<string, unknown>;
  return typeof message.id === "string" && (message.role === "user" || message.role === "assistant") && typeof message.content === "string" && typeof message.time === "string";
}

export default function PatientPortal({ session }: { session: Session }) {
  const [tab, setTab] = useState<Tab>("dashboard");
  const [schedule, setSchedule] = useState<ActiveSchedule | null>(null);
  const [summary, setSummary] = useState<AdherenceSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const patientId = session.user.id;
  const today = isoDate(new Date());

  const refresh = useCallback(async () => {
    const weekStart = new Date(); weekStart.setDate(weekStart.getDate() - 6);
    const [nextSchedule, nextSummary] = await Promise.all([api.schedule(patientId, today), api.adherenceSummary(patientId, isoDate(weekStart), today)]);
    setSchedule(nextSchedule); setSummary(nextSummary); setError(null);
  }, [patientId, today]);

  useEffect(() => { refresh().catch((cause: unknown) => setError(cause instanceof ApiError ? cause.message : "Không tải được lịch uống thuốc")); }, [refresh]);

  const doses = schedule?.doses ?? [];
  const nextDose = useMemo(() => doses.find((dose) => !["TAKEN", "SKIPPED", "MISSED"].includes(dose.status.toUpperCase())), [doses]);
  const completed = doses.filter((dose) => dose.status.toUpperCase() === "TAKEN").length;
  const adherence = Math.round(summary?.adherence_rate ?? 0);
  const notify = (text: string) => { setToast(text); window.setTimeout(() => setToast(null), 2800); };
  function logout() {
    try { window.sessionStorage.removeItem(chatStorageKey(patientId)); } catch { /* Storage may be unavailable. */ }
    setSession(null);
  }

  async function action(dose: ScheduledDoseRow, type: "TAKEN" | "SNOOZE" | "SKIPPED") {
    setBusyId(dose.scheduled_dose_id);
    try {
      await api.recordDoseAction(dose.scheduled_dose_id, type, type === "SNOOZE" ? { snooze_duration_minutes: 15 } : {});
      await refresh();
      notify(type === "TAKEN" ? "Đã ghi nhận bạn đã uống thuốc" : type === "SNOOZE" ? "Đã nhắc lại sau 15 phút" : "Đã ghi nhận cữ thuốc bỏ qua");
    } catch (cause) { notify(cause instanceof ApiError ? cause.message : "Không cập nhật được cữ thuốc"); }
    finally { setBusyId(null); }
  }

  return <div className="patient-web-shell">
    <aside className="patient-sidebar">
      <div className="patient-brand"><span className="patient-logo"><Icon name="pill" size={22}/></span><div><strong>RemindRx</strong><small>Patient Portal</small></div></div>
      <nav className="patient-side-nav" aria-label="Điều hướng bệnh nhân"><span className="patient-nav-label">MENU CHÍNH</span>{navItems.map((item) => <button key={item.id} className={`${tab === item.id ? "active" : ""} ${item.id === "sos" ? "sos-nav" : ""}`} onClick={() => setTab(item.id)}><span className="nav-icon"><Icon name={item.icon}/></span><span><b>{item.label}</b><small>{item.description}</small></span>{item.id === "schedule" && doses.length > 0 && <em>{doses.length}</em>}</button>)}</nav>
      <div className="patient-safe-card"><span><Icon name="shield" size={19}/></span><div><b>Dữ liệu được bảo vệ</b><small>Chỉ bạn và bác sĩ phụ trách có quyền truy cập.</small></div></div>
      <div className="patient-account"><span className="patient-avatar">BN</span><div><b>Bệnh nhân</b><small>{session.user.phone}</small></div><button aria-label="Đăng xuất" onClick={logout}><Icon name="logout" size={18}/></button></div>
    </aside>
    <div className="patient-workspace">
      <header className="patient-header"><h1>{navItems.find((item) => item.id === tab)?.label}</h1><div className="patient-header-actions"><span className="sync-state"><i/> Dữ liệu đã đồng bộ</span><button className="header-bell" aria-label="Thông báo"><Icon name="bell"/></button></div></header>
      <main className={`patient-content ${tab === "assistant" ? "chat-content" : ""}`}>
        {tab === "dashboard" && <DashboardView today={today} adherence={adherence} completed={completed} doses={doses} nextDose={nextDose} error={error} busyId={busyId} onRetry={refresh} onAction={action} onOpenSchedule={() => setTab("schedule")} onOpenSurvey={() => setTab("survey")}/>} 
        {tab === "schedule" && <ScheduleView doses={doses} busyId={busyId} onAction={action}/>} 
        {tab === "assistant" && <ChatView patientId={patientId}/>}
        {tab === "survey" && <SurveyView patientId={patientId} today={today} onDone={(message) => { notify(message); setTab("dashboard"); }}/>} 
        {tab === "sos" && <SosView patientId={patientId} onDone={(message) => { if (message) notify(message); setTab("dashboard"); }}/>} 
      </main>
    </div>{toast && <div className="patient-toast">{toast}</div>}
  </div>;
}

function DashboardView({ today, adherence, completed, doses, nextDose, error, busyId, onRetry, onAction, onOpenSchedule, onOpenSurvey }: { today: string; adherence: number; completed: number; doses: ScheduledDoseRow[]; nextDose?: ScheduledDoseRow; error: string | null; busyId: string | null; onRetry: () => Promise<void>; onAction: DoseAction; onOpenSchedule: () => void; onOpenSurvey: () => void }) {
  const readableDate = new Date(`${today}T12:00:00`).toLocaleDateString("vi-VN", { weekday: "long", day: "2-digit", month: "long", year: "numeric" });
  const missed = doses.filter((dose) => ["SKIPPED", "MISSED"].includes(dose.status.toUpperCase())).length;
  return <>
    <section className="web-welcome"><div><span>Xin chào 👋</span><h2>Chúc bạn một ngày khỏe mạnh</h2><p>{readableDate}</p></div><button onClick={onOpenSurvey}><Icon name="heart" size={18}/> Cập nhật sức khỏe</button></section>
    {error && <section className="patient-error"><b>Không thể đồng bộ dữ liệu</b><span>{error}</span><button onClick={() => void onRetry()}>Thử lại</button></section>}
    <section className="patient-kpi-grid">
      <Kpi icon="calendar" tone="blue" label="CỮ THUỐC HÔM NAY" value={doses.length} detail={`${completed} cữ đã hoàn thành`}/>
      <Kpi icon="check" tone="green" label="TUÂN THỦ 7 NGÀY" value={`${adherence}%`} detail={adherence >= 80 ? "Bạn đang làm rất tốt" : "Cố gắng duy trì đều đặn"}/>
      <Kpi icon="clock" tone="amber" label="LIỀU TIẾP THEO" value={nextDose ? prettyTime(nextDose.current_scheduled_at) : "—"} detail={nextDose?.medication_name ?? "Đã hoàn thành hôm nay"}/>
      <Kpi icon={missed ? "alert" : "shield"} tone={missed ? "red" : "green"} label="CẦN LƯU Ý" value={missed} detail={missed ? "cữ đã bỏ qua hoặc bị lỡ" : "Không có cảnh báo"}/>
    </section>
    <section className="dashboard-columns">
      <div className="web-card next-web-card"><CardHead eyebrow="NHẮC THUỐC" title="Liều tiếp theo" action="Xem lịch đầy đủ →" onAction={onOpenSchedule}/>{nextDose ? <NextDose dose={nextDose} busy={busyId === nextDose.scheduled_dose_id} onAction={onAction}/> : <div className="patient-complete"><b><Icon name="check"/> Bạn đã hoàn thành lịch hôm nay</b><span>Không còn cữ thuốc nào đang chờ.</span></div>}</div>
      <div className="web-card adherence-web-card"><CardHead eyebrow="TIẾN ĐỘ" title="Tuân thủ điều trị"/><div className="adherence-visual"><div className="progress-ring" style={{ "--progress": `${adherence * 3.6}deg` } as React.CSSProperties}><b>{adherence}%</b></div><div><strong>{adherence >= 80 ? "Rất tốt!" : "Tiếp tục cố gắng"}</strong><p>Đã uống {completed}/{doses.length} cữ hôm nay.</p></div></div><div className="adherence-legend"><span><i className="done"/> Đã uống <b>{completed}</b></span><span><i className="pending"/> Đang chờ <b>{Math.max(0, doses.length - completed - missed)}</b></span><span><i className="missed"/> Đã lỡ <b>{missed}</b></span></div></div>
    </section>
    <section className="web-card today-preview"><CardHead eyebrow="HÔM NAY" title="Lịch uống thuốc"/><div className="dose-table-head"><span>THỜI GIAN</span><span>THUỐC & LIỀU DÙNG</span><span>TRẠNG THÁI</span><span>THAO TÁC</span></div><div className="dose-list web-list">{doses.length ? doses.slice(0, 4).map((dose) => <DoseCard key={dose.scheduled_dose_id} dose={dose} busy={busyId === dose.scheduled_dose_id} onAction={onAction}/>) : <div className="patient-empty">Hôm nay chưa có lịch thuốc.</div>}</div></section>
    <p className="patient-safety-note"><Icon name="shield" size={15}/> Không tự ý đổi liều hoặc uống bù. Nếu có vấn đề, hãy liên hệ bác sĩ điều trị.</p>
  </>;
}

function Kpi({ icon, tone, label, value, detail }: { icon: IconName; tone: string; label: string; value: string | number; detail: string }) { return <article><span className={`kpi-icon ${tone}`}><Icon name={icon}/></span><div><small>{label}</small><strong>{value}</strong><p>{detail}</p></div></article>; }
function CardHead({ eyebrow, title, action, onAction }: { eyebrow: string; title: string; action?: string; onAction?: () => void }) { return <div className="web-card-head"><div><span className="section-eyebrow">{eyebrow}</span><h2>{title}</h2></div>{action && <button onClick={onAction}>{action}</button>}</div>; }

function ScheduleView({ doses, busyId, onAction }: { doses: ScheduledDoseRow[]; busyId: string | null; onAction: DoseAction }) { return <section className="web-card schedule-page-card"><div className="web-card-head"><div><span className="section-eyebrow">LỊCH CÁ NHÂN</span><h2>Lịch uống thuốc hôm nay</h2><p>Các cữ được tạo từ đơn thuốc đã được bác sĩ phê duyệt.</p></div><span className="date-chip">{new Date().toLocaleDateString("vi-VN")}</span></div><div className="schedule-timeline">{doses.length ? doses.map((dose, index) => <div className="timeline-row" key={dose.scheduled_dose_id}><div className="timeline-marker"><span>{prettyTime(dose.current_scheduled_at)}</span><i className={doseStatus(dose.status)[1]}/>{index < doses.length - 1 && <b/>}</div><DoseCard dose={dose} busy={busyId === dose.scheduled_dose_id} onAction={onAction}/></div>) : <div className="patient-empty">Hôm nay chưa có lịch thuốc. Lịch sẽ xuất hiện sau khi bác sĩ duyệt đơn.</div>}</div></section>; }
function NextDose({ dose, busy, onAction }: { dose: ScheduledDoseRow; busy: boolean; onAction: DoseAction }) { const locked = isDoseLocked(dose); return <div className={`next-dose ${locked ? "locked" : ""}`}><div className="next-dose-main"><span className="medicine-bubble"><Icon name="pill" size={25}/></span><div><span className="next-time"><Icon name="clock" size={17}/> {prettyTime(dose.current_scheduled_at)}</span><h2>{dose.medication_name}</h2><p>{doseLabel(dose)}</p></div></div>{locked ? <div className="dose-locked-note"><Icon name="clock" size={16}/> Có thể xác nhận khi đến giờ uống</div> : <DoseActions dose={dose} busy={busy} onAction={onAction}/>}</div>; }
function doseLabel(dose: ScheduledDoseRow) { return [dose.dose_value && `${dose.dose_value} ${dose.dose_unit ?? ""}`, dose.meal_relation].filter(Boolean).join(" · ") || "Dùng theo đơn đã duyệt"; }
function DoseCard({ dose, busy, onAction }: { dose: ScheduledDoseRow; busy: boolean; onAction: DoseAction }) { const locked = isDoseLocked(dose); const [label, status] = locked ? ["Chưa đến giờ", "locked"] as const : doseStatus(dose.status); return <article className={`patient-dose ${status}`}><div className="dose-time">{prettyTime(dose.current_scheduled_at)}</div><div className="dose-info"><span className="mini-pill"><Icon name="pill" size={17}/></span><div><h3>{dose.medication_name}</h3><p>{doseLabel(dose)}</p></div></div><span className={`dose-status ${status}`}>{label}</span>{!locked && (status === "upcoming" || status === "late") ? <DoseActions dose={dose} busy={busy} compact onAction={onAction}/> : <span className={`dose-done-mark ${locked ? "locked" : ""}`}><Icon name={locked ? "clock" : "check"} size={18}/></span>}</article>; }
function DoseActions({ dose, busy, compact = false, onAction }: { dose: ScheduledDoseRow; busy: boolean; compact?: boolean; onAction: DoseAction }) { return <div className={compact ? "dose-actions compact" : "dose-actions"}><button className="take" disabled={busy} onClick={() => void onAction(dose, "TAKEN")}><Icon name="check" size={16}/>{busy ? "Đang lưu…" : "Đã uống"}</button><button disabled={busy} onClick={() => void onAction(dose, "SNOOZE")}><Icon name="clock" size={15}/> Nhắc sau</button><button className="skip" disabled={busy} onClick={() => void onAction(dose, "SKIPPED")}>Bỏ qua</button></div>; }

function ChatView({ patientId }: { patientId: string }) {
  const [messages, setMessages] = useState<ChatMessage[]>(() => {
    try {
      const stored = window.sessionStorage.getItem(chatStorageKey(patientId));
      const parsed: unknown = stored ? JSON.parse(stored) : null;
      return Array.isArray(parsed) && parsed.length > 0 && parsed.every(isChatMessage) ? parsed : welcomeChatMessages();
    } catch { return welcomeChatMessages(); }
  });
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [recording, setRecording] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const recordingTimeoutRef = useRef<number | null>(null);
  const discardRecordingRef = useRef(false);
  const voiceSupported = useMemo(() => typeof window !== "undefined" && "MediaRecorder" in window && Boolean(navigator.mediaDevices?.getUserMedia), []);
  const suggestions = ["Liều tiếp theo lúc mấy giờ?", "Quên liều thì nên làm gì?", "Giải thích cách dùng thuốc của tôi"];

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages, busy]);
  useEffect(() => {
    try { window.sessionStorage.setItem(chatStorageKey(patientId), JSON.stringify(messages)); } catch { /* Storage may be unavailable. */ }
  }, [messages, patientId]);

  const stopRecording = useCallback(() => {
    if (recordingTimeoutRef.current !== null) {
      window.clearTimeout(recordingTimeoutRef.current);
      recordingTimeoutRef.current = null;
    }
    const recorder = recorderRef.current;
    if (recorder && recorder.state !== "inactive") recorder.stop();
  }, []);

  useEffect(() => () => {
    discardRecordingRef.current = true;
    stopRecording();
    recorderRef.current?.stream.getTracks().forEach((track) => track.stop());
  }, [stopRecording]);

  async function send(rawMessage: string) {
    const message = rawMessage.trim();
    if (!message || busy || recording) return;
    const userMessage: ChatMessage = { id: crypto.randomUUID(), role: "user", content: message, time: new Date().toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" }) };
    setMessages((current) => [...current, userMessage]);
    setInput(""); setError(null); setBusy(true);
    try {
      const result = await api.patientChat(message);
      setMessages((current) => [...current, { id: crypto.randomUUID(), role: "assistant", content: result.response, time: new Date().toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" }) }]);
    } catch (cause) { setError(cause instanceof ApiError ? cause.message : "Trợ lý AI chưa thể trả lời. Vui lòng thử lại."); }
    finally { setBusy(false); }
  }

  async function startRecording() {
    if (!voiceSupported || busy || recording) return;
    setError(null);
    discardRecordingRef.current = false;
    let stream: MediaStream | null = null;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const recorder = new MediaRecorder(stream);
      chunksRef.current = [];
      recorderRef.current = recorder;
      recorder.ondataavailable = (event) => { if (event.data.size > 0) chunksRef.current.push(event.data); };
      recorder.onstop = async () => {
        const currentStream = recorder.stream;
        if (recordingTimeoutRef.current !== null) {
          window.clearTimeout(recordingTimeoutRef.current);
          recordingTimeoutRef.current = null;
        }
        recorderRef.current = null;
        currentStream.getTracks().forEach((track) => track.stop());
        if (discardRecordingRef.current) return;
        setRecording(false);
        const audio = new Blob(chunksRef.current, { type: recorder.mimeType || "audio/webm" });
        if (audio.size === 0) {
          setError("Không nhận được âm thanh. Vui lòng thử lại.");
          return;
        }
        setBusy(true);
        try {
          const result = await api.patientChatVoice(audio);
          const time = new Date().toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" });
          setMessages((current) => [
            ...current,
            { id: crypto.randomUUID(), role: "user", content: result.transcript, time },
            { id: crypto.randomUUID(), role: "assistant", content: result.response, time },
          ]);
        } catch (cause) { setError(cause instanceof ApiError ? cause.message : "Trợ lý AI chưa thể trả lời. Vui lòng thử lại."); }
        finally { setBusy(false); }
      };
      recorder.start();
      setRecording(true);
      recordingTimeoutRef.current = window.setTimeout(stopRecording, 60_000);
    } catch (cause) {
      stream?.getTracks().forEach((track) => track.stop());
      recorderRef.current = null;
      setRecording(false);
      setError(cause instanceof DOMException && cause.name === "NotAllowedError" ? "Bạn cần cho phép dùng micro để gửi tin nhắn thoại." : "Không thể bắt đầu ghi âm. Vui lòng thử lại.");
    }
  }

  return <section className="chat-layout">
    <div className="web-card chat-panel">
      <header className="chat-panel-head"><div className="chat-avatar"><Icon name="assistant" size={22}/></div><div><h2>Trợ lý AI</h2><p>Thuốc & lịch uống · RemindRx</p></div><button onClick={() => setMessages(welcomeChatMessages())}>Cuộc trò chuyện mới</button></header>
      <div className="chat-warning"><Icon name="alert" size={17}/><span>AI chỉ cung cấp thông tin tham khảo; không tự thay đổi liều, kê đơn hoặc xử trí cấp cứu qua chat.</span></div>
      <div className="chat-messages">
        {messages.map((message) => <div key={message.id} className={`chat-row ${message.role}`}><div className="chat-bubble">{message.role === "assistant" && <b>RemindRx AI</b>}<p>{message.content}</p><time>{message.time}</time></div></div>)}
        {busy && <div className="chat-row assistant"><div className="chat-bubble chat-typing"><i/><i/><i/><span>Đang tra cứu…</span></div></div>}
        {error && <div className="chat-error">{error}</div>}
        <div ref={bottomRef}/>
      </div>
      <div className="chat-suggestions">{suggestions.map((suggestion) => <button key={suggestion} disabled={busy || recording} onClick={() => void send(suggestion)}>{suggestion}</button>)}</div>
      <form className="chat-composer" onSubmit={(event) => { event.preventDefault(); void send(input); }}><textarea value={input} disabled={recording} onChange={(event) => setInput(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); void send(input); } }} maxLength={5000} rows={1} placeholder="Hỏi về thuốc hoặc lịch uống…"/>{voiceSupported && <button className={`chat-mic ${recording ? "recording" : ""}`} type="button" disabled={busy} onClick={() => { if (recording) stopRecording(); else void startRecording(); }} aria-label={recording ? "Dừng ghi âm" : "Gửi tin nhắn thoại"}><Icon name="mic" size={19}/></button>}<button className="chat-send" type="submit" disabled={!input.trim() || busy || recording} aria-label="Gửi tin nhắn"><Icon name="send" size={19}/></button><small>{recording ? "Đang ghi âm · Nhấn micro để dừng" : "Nhấn Enter để gửi · Shift + Enter để xuống dòng"}</small></form>
    </div>
  </section>;
}

function SurveyView({ patientId, today, onDone }: { patientId: string; today: string; onDone: (message: string) => void }) {
  const [mood, setMood] = useState(3), [symptom, setSymptom] = useState("Không có"), [severity, setSeverity] = useState("MILD"), [busy, setBusy] = useState(false), [error, setError] = useState<string | null>(null);
  async function submit() { setBusy(true); setError(null); try { await api.submitHealthSurvey(patientId, { survey_date: today, answers_json: { mood }, symptoms: symptom === "Không có" ? [] : [{ symptom_code: symptomCodes[symptom], severity }] }); onDone("Đã gửi khảo sát cho bác sĩ điều trị"); } catch (cause) { setError(cause instanceof ApiError ? cause.message : "Không gửi được khảo sát"); } finally { setBusy(false); } }
  const moodIcons = ["😞", "🙁", "😐", "🙂", "😊"];
  return <section className="web-card patient-form"><div className="form-hero"><span><Icon name="heart" size={25}/></span><div><h1>Khảo sát sức khỏe hôm nay</h1><p>Chỉ mất khoảng 1 phút. Thông tin giúp bác sĩ theo dõi bạn tốt hơn.</p></div></div><div className="form-section"><span className="form-step">01</span><h2>Hôm nay bạn cảm thấy thế nào?</h2><div className="mood-row">{[1,2,3,4,5].map((value) => <button key={value} className={mood === value ? "picked" : ""} onClick={() => setMood(value)}><span>{moodIcons[value - 1]}</span><b>{value}</b></button>)}</div><div className="mood-label"><span>Rất tệ</span><span>Rất tốt</span></div></div><div className="form-section"><span className="form-step">02</span><h2>Bạn có gặp tác dụng phụ nào không?</h2><div className="symptoms">{symptoms.map((item) => <button key={item} className={symptom === item ? "picked" : ""} onClick={() => setSymptom(item)}>{item}</button>)}</div>{symptom !== "Không có" && <><h3>Mức độ triệu chứng</h3><div className="severity-row">{[["MILD","Nhẹ"],["MODERATE","Vừa"],["SEVERE","Nặng"]].map(([value,label]) => <button key={value} className={`${severity === value ? "picked" : ""} ${value === "SEVERE" ? "severe" : ""}`} onClick={() => setSeverity(value)}>{label}</button>)}</div>{severity === "SEVERE" && <div className="survey-warning"><Icon name="alert" size={18}/> Mức “Nặng” sẽ cảnh báo ngay cho bác sĩ điều trị.</div>}</>}</div>{error && <div className="patient-error"><span>{error}</span></div>}<div className="form-submit-row"><p><Icon name="shield" size={16}/> Dữ liệu được bảo mật</p><button className="survey-submit" disabled={busy} onClick={() => void submit()}>{busy ? "Đang gửi…" : "Gửi cập nhật sức khỏe"}</button></div></section>;
}

function SosView({ patientId, onDone }: { patientId: string; onDone: (message: string) => void }) {
  const [holding, setHolding] = useState(false), [sent, setSent] = useState(false), [busy, setBusy] = useState(false), [error, setError] = useState<string | null>(null);
  useEffect(() => { if (!holding || busy || sent) return; const timer = window.setTimeout(async () => { setBusy(true); try { await api.triggerSos(patientId); setSent(true); } catch (cause) { setError(cause instanceof ApiError ? cause.message : "Không gửi được cảnh báo SOS"); } finally { setBusy(false); setHolding(false); } }, 3000); return () => window.clearTimeout(timer); }, [holding, busy, patientId, sent]);
  return <section className="sos-page"><div className="sos-info-panel"><span className="sos-shield"><Icon name="shield" size={28}/></span><h2>Hỗ trợ khẩn cấp</h2><p>Giữ nút SOS trong 3 giây. Hệ thống sẽ gửi cảnh báo tới đội ngũ chăm sóc và bác sĩ phụ trách.</p><ul><li><Icon name="check" size={17}/> Ghi nhận cảnh báo trên hệ thống</li><li><Icon name="check" size={17}/> Thông báo tới bác sĩ phụ trách</li><li><Icon name="check" size={17}/> Theo dõi trạng thái xử lý</li></ul><div className="sos-disclaimer"><Icon name="alert" size={18}/><span><b>Trong tình huống nguy hiểm tính mạng</b>Hãy gọi ngay số cấp cứu 115. SOS trong ứng dụng không thay thế dịch vụ cấp cứu.</span></div></div><div className="sos-action-panel"><button className={`sos-button ${holding ? "holding" : ""}`} disabled={busy || sent} onPointerDown={() => setHolding(true)} onPointerUp={() => setHolding(false)} onPointerLeave={() => setHolding(false)} onPointerCancel={() => setHolding(false)}><span>{sent ? "ĐÃ GỬI" : busy ? "ĐANG GỬI" : "SOS"}</span><small>{sent ? "CẢNH BÁO SOS" : "GIỮ 3 GIÂY ĐỂ GỬI"}</small></button><h1>{sent ? "Cảnh báo đã được ghi nhận" : "Bạn cần trợ giúp?"}</h1><p>{sent ? "Hệ thống đã ghi nhận cảnh báo và đang chuyển tới đội ngũ chăm sóc." : "Nhấn giữ nút phía trên để xác nhận gửi cảnh báo."}</p>{error && <b className="sos-error">{error}</b>}<button className="sos-cancel" onClick={() => onDone(sent ? "Đã đóng cảnh báo SOS" : "")}>{sent ? "Quay về tổng quan" : "Huỷ và quay lại"}</button></div></section>;
}
