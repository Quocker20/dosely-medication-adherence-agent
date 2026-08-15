import { useCallback, useEffect, useState } from "react";

import { ApiError, api, waitForAgentRun } from "./api";
import AdminPortal from "./components/admin/AdminPortal";
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
  const [, setPathname] = useState(() => window.location.pathname);

  // api.ts tự xoá phiên khi refresh token hết hạn — App phải nghe để quay về màn đăng nhập.
  useEffect(() => subscribe(setLocalSession), []);

  useEffect(() => {
    const onPopState = () => setPathname(window.location.pathname);
    window.addEventListener("popstate", onPopState);
    return () => window.removeEventListener("popstate", onPopState);
  }, []);

  useEffect(() => {
    if (!session) return;
    const expected = session.user.role === "ADMIN" ? "/admin/" : "/doctor/";
    if (window.location.pathname !== expected) {
      window.history.replaceState({}, "", expected);
      setPathname(expected);
    }
  }, [session, setPathname]);

  if (!session) return <LoginScreen />;
  if (session.user.role === "ADMIN") return <AdminPortal session={session} />;
  if (session.user.role === "DOCTOR") return <Portal session={session} />;
  return <LoginScreen />;
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
  const [patientSearch, setPatientSearch] = useState("");
  const [alertFilter, setAlertFilter] = useState("");
  const [patientPage, setPatientPage] = useState(1);

  const [rxPhone, setRxPhone] = useState("");
  const [alertBusyId, setAlertBusyId] = useState<string | null>(null);
  const [toasts, setToasts] = useState<{ id: number; text: string }[]>([]);

  const toast = useCallback((text: string) => {
    const id = Date.now() + Math.random();
    setToasts((current) => [...current, { id, text }]);
    setTimeout(() => setToasts((current) => current.filter((item) => item.id !== id)), 2600);
  }, []);

  const refresh = useCallback(async () => {
    const [patientPageResult, alertPage] = await Promise.all([
      api.dashboardPatients({
        page: patientPage,
        size: 20,
        search: patientSearch,
        alertStatus: alertFilter || undefined,
      }),
      api.alerts({ size: 50, status: alertFilter || undefined }),
    ]);
    setPatients(patientPageResult.content);
    setTotalPatients(patientPageResult.total_elements);
    setAlerts(alertPage.content);
  }, [alertFilter, patientPage, patientSearch]);

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
      const dispatched = await api.generateSchedule(patientId, "Bác sĩ yêu cầu tính lại lịch từ portal");
      const run = await waitForAgentRun(dispatched.agent_run_id);
      if (run.status === "COMPLETED") {
        setSchedule(await api.schedule(patientId, isoDate(new Date())));
        toast(`Đã tính lại lịch · ${run.generated_dose_count ?? 0} cữ`);
      } else {
        toast(`Agent chưa hoàn tất lịch · ${run.status}`);
      }
    } catch (error) {
      toast(error instanceof ApiError ? error.message : "Không tính được lịch");
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
              <input
                className="topbar-search"
                aria-label="Tìm bệnh nhân"
                placeholder="Tìm bệnh nhân / SĐT"
                value={patientSearch}
                onChange={(event) => {
                  setPatientPage(1);
                  setPatientSearch(event.target.value);
                }}
              />
              <select
                aria-label="Lọc cảnh báo"
                value={alertFilter}
                onChange={(event) => {
                  setPatientPage(1);
                  setAlertFilter(event.target.value);
                }}
              >
                <option value="">Tất cả trạng thái</option>
                <option value="OPEN">Đang mở</option>
                <option value="ACKNOWLEDGED">Đã tiếp nhận</option>
                <option value="RESOLVED">Đã đóng</option>
              </select>
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
              <div className="row-actions pagination">
                <button className="btn sm" disabled={patientPage <= 1} onClick={() => setPatientPage((page) => page - 1)}>
                  ← Trang trước
                </button>
                <span className="rail-note">Trang {patientPage}</span>
                <button
                  className="btn sm"
                  disabled={totalPatients <= patientPage * 20}
                  onClick={() => setPatientPage((page) => page + 1)}
                >
                  Trang sau →
                </button>
              </div>
              <GuardBanner title="Ranh giới của AI trong hệ thống này">
                <li>
                  Planning Agent chỉ <b>tính giờ nhắc</b> từ đơn đã được bác sĩ duyệt và lịch sinh hoạt bệnh nhân.
                </li>
                <li>
                  Planning Agent chỉ được <b>tính lại giờ</b> — không đổi liều, số cữ, đường dùng hay số ngày điều trị.
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
        onGenerateSchedule={requestReschedule}
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
