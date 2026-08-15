import { useCallback, useEffect, useState } from "react";

import { ApiError, api } from "./api";
import AlertsView from "./components/AlertsView";
import GuardBanner from "./components/GuardBanner";
import KpiRow from "./components/KpiRow";
import LoginScreen from "./components/LoginScreen";
import PatientDrawer from "./components/PatientDrawer";
import PatientTable from "./components/PatientTable";
import PrescriptionView from "./components/PrescriptionView";
import Sidebar from "./components/Sidebar";
import { isoDate } from "./lib/labels";
import { getSession, setSession, subscribe, type Session } from "./session";
import type {
  ActiveSchedule,
  AlertDetail,
  DashboardPatientDetail,
  DashboardPatientListItem,
  PatientRoutine,
} from "./types";

export type ViewName = "dashboard" | "alerts" | "rx";
export type ThemeMode = "system" | "light" | "dark";

const TITLES: Record<ViewName, [string, string]> = {
  dashboard: ["Dashboard theo dõi", "Theo dõi tuân thủ điều trị theo thời gian thực"],
  alerts: ["Cảnh báo khẩn", "Closed-loop Red Alert · chỉ bác sĩ được đóng cảnh báo"],
  rx: ["Kê đơn thuốc điện tử", "Đơn phải được bác sĩ duyệt trước khi sinh lịch nhắc"],
};

const NEXT_THEME: Record<ThemeMode, ThemeMode> = { system: "light", light: "dark", dark: "system" };

export default function App() {
  const [session, setLocalSession] = useState<Session | null>(getSession);

  // api.ts tự xoá phiên khi refresh token hết hạn — App phải nghe để quay về màn đăng nhập.
  useEffect(() => subscribe(setLocalSession), []);

  if (!session) return <LoginScreen />;
  return <Portal session={session} />;
}

function Portal({ session }: { session: Session }) {
  const [view, setView] = useState<ViewName>("dashboard");
  const [theme, setTheme] = useState<ThemeMode>("system");

  const [patients, setPatients] = useState<DashboardPatientListItem[]>([]);
  const [totalPatients, setTotalPatients] = useState(0);
  const [alerts, setAlerts] = useState<AlertDetail[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [detail, setDetail] = useState<DashboardPatientDetail | null>(null);
  const [routine, setRoutine] = useState<PatientRoutine | null>(null);
  const [schedule, setSchedule] = useState<ActiveSchedule | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [drawerBusy, setDrawerBusy] = useState(false);

  const [rxPhone, setRxPhone] = useState("");
  const [alertBusyId, setAlertBusyId] = useState<string | null>(null);
  const [toasts, setToasts] = useState<{ id: number; text: string }[]>([]);

  const toast = useCallback((text: string) => {
    const id = Date.now() + Math.random();
    setToasts((current) => [...current, { id, text }]);
    setTimeout(() => setToasts((current) => current.filter((item) => item.id !== id)), 2600);
  }, []);

  const refresh = useCallback(async () => {
    const [patientPage, alertPage] = await Promise.all([
      api.dashboardPatients({ size: 50 }),
      api.alerts({ size: 50 }),
    ]);
    setPatients(patientPage.content);
    setTotalPatients(patientPage.total_elements);
    setAlerts(alertPage.content);
  }, []);

  useEffect(() => {
    let cancelled = false;

    (async () => {
      try {
        await refresh();
        if (!cancelled) setLoadError(null);
      } catch (error) {
        if (!cancelled) {
          setLoadError(error instanceof ApiError ? error.message : "Không tải được dữ liệu");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [refresh]);

  useEffect(() => {
    const timer = window.setInterval(() => {
      refresh().catch(() => {
        // Lần tải đầu đã có error panel; polling im lặng và tự phục hồi ở nhịp sau.
      });
    }, 10_000);
    return () => window.clearInterval(timer);
  }, [refresh]);

  // WS /ws/dashboard nằm ngoài /api/v1 và nhận token qua query — browser
  // WebSocket không set được header Authorization.
  useEffect(() => {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const url = `${protocol}//${window.location.host}/ws/dashboard?token=${encodeURIComponent(session.accessToken)}`;

    let socket: WebSocket;
    try {
      socket = new WebSocket(url);
    } catch {
      return;
    }

    socket.onmessage = () => {
      // Frame hiện có là alert.opened / alert.updated — kéo lại roster cho đồng bộ.
      refresh().catch(() => {});
    };

    return () => socket.close();
  }, [session.accessToken, refresh]);

  useEffect(() => {
    const root = document.documentElement;
    if (theme === "system") root.removeAttribute("data-theme");
    else root.setAttribute("data-theme", theme);
  }, [theme]);

  async function openPatient(patientId: string) {
    setDrawerOpen(true);
    setDetail(null);
    setRoutine(null);
    setSchedule(null);

    try {
      const nextDetail = await api.dashboardPatientDetail(patientId);
      setDetail(nextDetail);

      // Routine và lịch hôm nay là dữ liệu phụ — thiếu thì vẫn mở được hồ sơ.
      const [routineResult, scheduleResult] = await Promise.allSettled([
        api.patientRoutine(patientId),
        api.schedule(patientId, isoDate(new Date())),
      ]);
      if (routineResult.status === "fulfilled") setRoutine(routineResult.value);
      if (scheduleResult.status === "fulfilled") setSchedule(scheduleResult.value);
    } catch (error) {
      setDrawerOpen(false);
      toast(error instanceof ApiError ? error.message : "Không mở được hồ sơ");
    }
  }

  async function acknowledgeAlert(id: string) {
    setAlertBusyId(id);
    try {
      await api.acknowledgeAlert(id);
      await refresh();
      toast("Đã tiếp nhận cảnh báo");
    } catch (error) {
      toast(error instanceof ApiError ? error.message : "Không cập nhật được cảnh báo");
    } finally {
      setAlertBusyId(null);
    }
  }

  async function resolveAlert(id: string, resolutionNote: string) {
    setAlertBusyId(id);
    try {
      await api.resolveAlert(id, resolutionNote);
      await refresh();
      toast("Đã đóng cảnh báo");
    } catch (error) {
      toast(error instanceof ApiError ? error.message : "Không đóng được cảnh báo");
    } finally {
      setAlertBusyId(null);
    }
  }

  async function requestReschedule(patientId: string) {
    setDrawerBusy(true);
    try {
      const dispatched = await api.reschedule(patientId, "Bác sĩ yêu cầu dời giờ từ portal");
      toast(`Đã gửi yêu cầu dời giờ · run ${dispatched.agent_run_id.slice(0, 8)}`);
    } catch (error) {
      toast(error instanceof ApiError ? error.message : "Không gửi được yêu cầu dời giờ");
    } finally {
      setDrawerBusy(false);
    }
  }

  async function logout() {
    try {
      await api.logout(session.refreshToken);
    } catch {
      // Token có thể đã bị thu hồi phía server — vẫn phải xoá phiên phía client.
    } finally {
      setSession(null);
    }
  }

  const openAlerts = alerts.filter((alert) => alert.status === "OPEN").length;
  const liveAlerts = alerts.filter(
    (alert) => alert.status === "OPEN" || alert.status === "ACKNOWLEDGED",
  ).length;
  const watching = patients.filter((p) => p.open_alerts_count === 0 && p.adherence_rate < 70).length;
  const [title, subtitle] = TITLES[view];

  return (
    <>
      <div className="app">
        <Sidebar
          view={view}
          openAlerts={openAlerts}
          patientsTotal={totalPatients}
          theme={theme}
          user={session.user}
          onView={setView}
          onTheme={() => setTheme((current) => NEXT_THEME[current])}
          onLogout={logout}
        />

        <main className="main">
          <header className="topbar">
            <div>
              <h1>{title}</h1>
              <p className="topbar-meta">
                {view === "dashboard" ? `${totalPatients} bệnh nhân đang điều trị · ` : ""}
                {subtitle}
              </p>
            </div>
            <div className="topbar-actions">
              <button
                className="btn sm"
                onClick={() => {
                  refresh()
                    .then(() => toast("Đã đồng bộ dữ liệu mới nhất"))
                    .catch((error) =>
                      toast(error instanceof ApiError ? error.message : "Không đồng bộ được dữ liệu"),
                    );
                }}
              >
                ↻ Làm mới
              </button>
              <span className={`pill ${liveAlerts ? "crit" : "ok"}`}>
                <span className="dot" />
                {liveAlerts} cảnh báo chưa xong
              </span>
              <span className="pill warn">
                <span className="dot" />
                {watching} cần theo dõi
              </span>
            </div>
          </header>

          {loadError && (
            <section className="view">
              <div className="errors">
                <b>Không tải được dữ liệu từ API</b>
                <ul>
                  <li>{loadError}</li>
                  <li>Chạy backend trước: `make run` (uvicorn cổng 8000), rồi tải lại trang.</li>
                </ul>
              </div>
            </section>
          )}

          {view === "dashboard" && (
            <section className="view">
              <KpiRow patients={patients} alerts={alerts} totalPatients={totalPatients} loading={loading} />
              <PatientTable patients={patients} onOpen={openPatient} />
              <GuardBanner title="Ranh giới của AI trong hệ thống này">
                <li>
                  Planning Agent chỉ <b>tính giờ nhắc</b> từ đơn đã được bác sĩ duyệt và lịch sinh hoạt bệnh nhân.
                </li>
                <li>
                  Rescheduling Agent chỉ được <b>dời giờ</b> — không đổi liều, số cữ, đường dùng hay số ngày điều trị.
                </li>
                <li>
                  Xung đột không giải được thì agent dừng và giữ nguyên lịch cũ, không tự suy đoán.
                </li>
              </GuardBanner>
            </section>
          )}

          {view === "alerts" && (
            <AlertsView
              alerts={alerts}
              patients={patients}
              busyId={alertBusyId}
              onAcknowledge={acknowledgeAlert}
              onResolve={resolveAlert}
              onOpenPatient={openPatient}
            />
          )}

          {view === "rx" && (
            <PrescriptionView
              phone={rxPhone}
              onPhone={setRxPhone}
              onToast={toast}
              onPrescribed={() => {
                refresh().catch(() => {});
              }}
            />
          )}
        </main>
      </div>

      <PatientDrawer
        detail={detail}
        routine={routine}
        schedule={schedule}
        open={drawerOpen}
        busy={drawerBusy}
        onClose={() => setDrawerOpen(false)}
        onPrescribe={(phone) => {
          setDrawerOpen(false);
          setRxPhone(phone);
          setView("rx");
        }}
        onReschedule={requestReschedule}
      />

      <div className="toast-wrap">
        {toasts.map((item) => (
          <div className="toast" key={item.id}>
            {item.text}
          </div>
        ))}
      </div>
    </>
  );
}
