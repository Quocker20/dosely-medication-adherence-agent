import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { ApiError, api } from "../../api";
import { THEME_LABEL, useTheme } from "../../hooks/useTheme";
import { useToasts } from "../../hooks/useToasts";
import { setSession, type Session } from "../../session";
import type { ActiveSchedule, AdherenceSummary, ScheduledDoseRow } from "../../types";
import CaregiverView from "./components/CaregiverView";
import ChatView, { chatStorageKey } from "./components/ChatView";
import DashboardView from "./components/DashboardView";
import DoseReminderStack from "./components/DoseReminderStack";
import Icon, { type IconName } from "./components/Icon";
import OnboardingView from "./components/OnboardingView";
import RoutineView from "./components/RoutineView";
import ScheduleView from "./components/ScheduleView";
import SosView from "./components/SosView";
import SurveyView from "./components/SurveyView";
import { useFcmReminders } from "./components/useFcmReminders";
import { isoDate } from "./components/utils";

type Tab = "dashboard" | "schedule" | "routine" | "caregivers" | "assistant" | "survey" | "sos";

const navItems: Array<{ id: Tab; label: string; description: string; icon: IconName }> = [
  { id: "dashboard", label: "Tổng quan", description: "Sức khỏe hôm nay", icon: "home" },
  { id: "schedule", label: "Lịch uống thuốc", description: "Các cữ trong ngày", icon: "calendar" },
  { id: "routine", label: "Lịch sinh hoạt", description: "Đồng bộ với ứng dụng", icon: "clock" },
  { id: "caregivers", label: "Người chăm sóc", description: "Bảo hộ qua Telegram", icon: "users" },
  { id: "assistant", label: "Trợ lý AI", description: "Hỏi về thuốc & lịch", icon: "assistant" },
  { id: "survey", label: "Khảo sát sức khỏe", description: "Cập nhật cho bác sĩ", icon: "heart" },
  { id: "sos", label: "Hỗ trợ khẩn cấp", description: "Gửi cảnh báo SOS", icon: "alert" },
];

interface Props {
  session: Session;
  tab: Tab;
  onTabChange: (tab: Tab) => void;
}

export default function PatientPortal({ session, tab, onTabChange }: Props) {
  const { theme, cycleTheme } = useTheme();
  const [schedule, setSchedule] = useState<ActiveSchedule | null>(null);
  const [summary, setSummary] = useState<AdherenceSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [showNotifications, setShowNotifications] = useState(false);
  const notifPanelRef = useRef<HTMLDivElement>(null);
  const { toasts, notify } = useToasts();
  const patientId = session.user.id;
  const today = isoDate(new Date());

  const reminders = useFcmReminders(patientId, session.accessToken);

  const refresh = useCallback(async () => {
    const weekStart = new Date(); weekStart.setDate(weekStart.getDate() - 6);
    const [nextSchedule, nextSummary] = await Promise.all([api.schedule(patientId, today), api.adherenceSummary(patientId, isoDate(weekStart), today)]);
    setSchedule(nextSchedule); setSummary(nextSummary); setError(null);
  }, [patientId, today]);

  useEffect(() => { refresh().catch((cause: unknown) => setError(cause instanceof ApiError ? cause.message : "Không tải được lịch uống thuốc")); }, [refresh]);

  // isDoseLocked() (utils.ts) reads Date.now() live and is always correct,
  // but React only re-renders on state/prop changes — nothing re-invokes it
  // as the wall clock crosses a dose's unlock time. Force a re-render every
  // 30s so a locked dose card flips to actionable without a page reload.
  const [, forceDoseLockRecheck] = useState(0);
  useEffect(() => {
    const id = window.setInterval(() => forceDoseLockRecheck((t) => t + 1), 30_000);
    return () => window.clearInterval(id);
  }, []);

  // Close notifications panel on outside click
  useEffect(() => {
    if (!showNotifications) return;
    function handleClickOutside(event: MouseEvent) {
      if (notifPanelRef.current && !notifPanelRef.current.contains(event.target as Node)) {
        setShowNotifications(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [showNotifications]);

  const doses = schedule?.doses ?? [];
  const nextDose = useMemo(() => doses.find((dose) => !["TAKEN", "SKIPPED", "MISSED"].includes(dose.status.toUpperCase())), [doses]);
  const completed = doses.filter((dose) => dose.status.toUpperCase() === "TAKEN").length;
  const adherence = Math.round(summary?.adherence_rate ?? 0);

  const handleBellClick = () => {
    setShowNotifications((prev) => !prev);
    if (!showNotifications) {
      reminders.markAllRead();
    }
    reminders.requestPermissionAndRegister().catch(() => {});
  };

  async function logout() {
    try {
      window.sessionStorage.removeItem(chatStorageKey(patientId));
      await api.logout(session.refreshToken);
    } catch {
      /* Session cục bộ vẫn phải bị xóa khi token server đã hết hạn hoặc offline. */
    } finally {
      setSession(null);
    }
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

  if (session.needOnboarding) {
    return (
      <div className="patient-web-shell" style={{ display: "block", overflowY: "auto" }}>
        <div className="patient-workspace" style={{ height: "auto" }}>
          <main className="patient-content" style={{ paddingTop: 40 }}>
            <OnboardingView patientId={patientId} onDone={() => setSession({ ...session, needOnboarding: false })} />
          </main>
        </div>
      </div>
    );
  }

  return (
    <div className="patient-web-shell">
      <aside className="patient-sidebar">
        <div className="patient-brand"><span className="patient-logo"><Icon name="pill" size={22}/></span><div><strong>Dosely</strong><small>Trang bệnh nhân</small></div></div>
        <nav className="patient-side-nav" aria-label="Điều hướng bệnh nhân"><span className="patient-nav-label">MENU CHÍNH</span>{navItems.map((item) => <button key={item.id} className={`${tab === item.id ? "active" : ""} ${item.id === "sos" ? "sos-nav" : ""}`} onClick={() => onTabChange(item.id)}><span className="nav-icon"><Icon name={item.icon}/></span><span><b>{item.label}</b><small>{item.description}</small></span>{item.id === "schedule" && doses.length > 0 && <em>{doses.length}</em>}</button>)}</nav>
        <div className="patient-safe-card"><span><Icon name="shield" size={19}/></span><div><b>Dữ liệu được bảo vệ</b><small>Chỉ bạn và bác sĩ phụ trách có quyền truy cập.</small></div></div>
        <button className="theme-toggle patient-theme-toggle" onClick={cycleTheme}>
          <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" width="14" height="14" aria-hidden="true">
            <circle cx="8" cy="8" r="3.2" />
            <path
              d="M8 1v1.6M8 13.4V15M15 8h-1.6M2.6 8H1M12.9 3.1l-1.1 1.1M4.2 11.8l-1.1 1.1M12.9 12.9l-1.1-1.1M4.2 4.2 3.1 3.1"
              strokeLinecap="round"
            />
          </svg>
          <span>Giao diện: {THEME_LABEL[theme]}</span>
        </button>
        <div className="patient-account"><span className="patient-avatar">BN</span><div><b>Bệnh nhân</b><small>{session.user.phone}</small></div><button aria-label="Đăng xuất" onClick={logout}><Icon name="logout" size={18}/></button></div>
      </aside>
      <div className="patient-workspace">
        <header className="patient-header">
          <h1>{navItems.find((item) => item.id === tab)?.label}</h1>
          <div className="patient-header-actions">
            <span className="sync-state"><i/> Dữ liệu đã đồng bộ</span>
            <div className="header-bell-wrap" ref={notifPanelRef}>
              <button
                className="header-bell"
                aria-label={`Thông báo${reminders.unreadCount > 0 ? ` (${reminders.unreadCount} chưa đọc)` : ""}`}
                onClick={handleBellClick}
              >
                <Icon name="bell"/>
                {reminders.unreadCount > 0 && (
                  <span className="notification-badge" aria-hidden="true">
                    {reminders.unreadCount > 99 ? "99+" : reminders.unreadCount}
                  </span>
                )}
              </button>

              {showNotifications && (
                <div className="notification-panel" role="dialog" aria-label="Danh sách thông báo">
                  <div className="notification-panel-header">
                    <strong>Thông báo</strong>
                    {reminders.history.length > 0 && (
                      <span className="notification-panel-count">{reminders.history.length} mục</span>
                    )}
                  </div>
                  <div className="notification-panel-list">
                    {reminders.history.length === 0 ? (
                      <div className="notification-empty">Không có thông báo nào</div>
                    ) : (
                      reminders.history.map((item) => (
                        <div key={item.id} className={`notification-item ${item.read ? "read" : "unread"}`}>
                          <div className="notification-item-dot" aria-hidden="true" />
                          <div className="notification-item-content">
                            <div className="notification-item-title">{item.title}</div>
                            <div className="notification-item-body">{item.body}</div>
                            <div className="notification-item-time">
                              {new Date(item.firedAt).toLocaleTimeString("vi-VN", {
                                hour: "2-digit",
                                minute: "2-digit",
                                day: "2-digit",
                                month: "2-digit",
                              })}
                            </div>
                          </div>
                        </div>
                      ))
                    )}
                  </div>
                </div>
              )}
            </div>
          </div>
        </header>
        <main className={`patient-content ${tab === "assistant" ? "chat-content" : ""}`}>
          {tab === "dashboard" && <DashboardView today={today} adherence={adherence} completed={completed} doses={doses} nextDose={nextDose} error={error} busyId={busyId} onRetry={refresh} onAction={action} onOpenSchedule={() => onTabChange("schedule")} onOpenSurvey={() => onTabChange("survey")}/>}
          {tab === "schedule" && <ScheduleView doses={doses} busyId={busyId} onAction={action}/>}
          {tab === "routine" && <RoutineView patientId={patientId} accessToken={session.accessToken} onScheduleChanged={() => refresh().catch(() => {})} onNotice={notify} />}
          {tab === "caregivers" && <CaregiverView patientId={patientId} onNotice={notify} />}
          {tab === "assistant" && <ChatView patientId={patientId}/>}
          {tab === "survey" && <SurveyView patientId={patientId} today={today} onDone={(message) => { notify(message); onTabChange("dashboard"); }}/>}
          {tab === "sos" && <SosView patientId={patientId} onDone={(message) => { if (message) notify(message); onTabChange("dashboard"); }}/>}
        </main>
      </div>
      <DoseReminderStack reminders={reminders.active} onDismiss={reminders.dismiss} />
      {/* Chỉ hiện toast mới nhất — giữ đúng hành vi "một toast tại một thời điểm" như trước khi gộp hook. */}
      {toasts.length > 0 && <div className="patient-toast">{toasts[toasts.length - 1].text}</div>}
    </div>
  );
}

