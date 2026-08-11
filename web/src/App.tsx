import { useCallback, useEffect, useState } from "react";

import { api } from "./api";
import AlertsView from "./components/AlertsView";
import GuardBanner from "./components/GuardBanner";
import KpiRow from "./components/KpiRow";
import PatientDrawer from "./components/PatientDrawer";
import PatientTable from "./components/PatientTable";
import PrescriptionView from "./components/PrescriptionView";
import Sidebar from "./components/Sidebar";
import type { Alert, DashboardSummary, DrugCatalogEntry, Patient, PatientDetail } from "./types";

export type ViewName = "dashboard" | "alerts" | "rx";
export type ThemeMode = "system" | "light" | "dark";

const TITLES: Record<ViewName, [string, string]> = {
  dashboard: ["Dashboard theo dõi", "Theo dõi tuân thủ điều trị theo thời gian thực"],
  alerts: ["Cảnh báo khẩn", "Closed-loop Red Alert · chỉ bác sĩ được đóng cảnh báo"],
  rx: ["Kê đơn thuốc điện tử", "FR-1.1 · đơn phải được bác sĩ duyệt trước khi sinh lịch nhắc"],
};

const NEXT_THEME: Record<ThemeMode, ThemeMode> = { system: "light", light: "dark", dark: "system" };

export default function App() {
  const [view, setView] = useState<ViewName>("dashboard");
  const [theme, setTheme] = useState<ThemeMode>("system");

  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [patients, setPatients] = useState<Patient[]>([]);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [drugs, setDrugs] = useState<DrugCatalogEntry[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [detail, setDetail] = useState<PatientDetail | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [rxPatientId, setRxPatientId] = useState("");
  const [alertBusyId, setAlertBusyId] = useState<string | null>(null);
  const [toasts, setToasts] = useState<{ id: number; text: string }[]>([]);

  const toast = useCallback((text: string) => {
    const id = Date.now() + Math.random();
    setToasts((current) => [...current, { id, text }]);
    setTimeout(() => setToasts((current) => current.filter((item) => item.id !== id)), 2600);
  }, []);

  const refreshDashboard = useCallback(async () => {
    const [nextSummary, nextAlerts, nextPatients] = await Promise.all([api.summary(), api.alerts(), api.patients()]);
    setSummary(nextSummary);
    setAlerts(nextAlerts);
    setPatients(nextPatients);
  }, []);

  useEffect(() => {
    let cancelled = false;

    (async () => {
      try {
        const [nextSummary, nextPatients, nextAlerts, nextDrugs] = await Promise.all([
          api.summary(),
          api.patients(),
          api.alerts(),
          api.drugs(),
        ]);
        if (cancelled) return;
        setSummary(nextSummary);
        setPatients(nextPatients);
        setAlerts(nextAlerts);
        setDrugs(nextDrugs);
        setRxPatientId((current) => current || nextPatients[0]?.id || "");
      } catch (error) {
        if (!cancelled) {
          setLoadError(error instanceof Error ? error.message : "Không tải được dữ liệu");
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    const timer = window.setInterval(() => {
      refreshDashboard().catch(() => {
        // Lần tải đầu đã có error panel; polling im lặng và tự phục hồi ở nhịp sau.
      });
    }, 10_000);
    return () => window.clearInterval(timer);
  }, [refreshDashboard]);

  useEffect(() => {
    const root = document.documentElement;
    if (theme === "system") root.removeAttribute("data-theme");
    else root.setAttribute("data-theme", theme);
  }, [theme]);

  async function openPatient(patientId: string) {
    try {
      setDetail(await api.patientDetail(patientId));
      setDrawerOpen(true);
    } catch (error) {
      toast(error instanceof Error ? error.message : "Không mở được hồ sơ");
    }
  }

  async function acknowledgeAlert(id: string) {
    setAlertBusyId(id);
    try {
      await api.acknowledgeAlert(id);
      await refreshDashboard();
      toast(`Đã tiếp nhận ${id}`);
    } catch (error) {
      toast(error instanceof Error ? error.message : "Không cập nhật được cảnh báo");
    } finally {
      setAlertBusyId(null);
    }
  }

  async function resolveAlert(id: string, falsePositive: boolean) {
    setAlertBusyId(id);
    try {
      await api.resolveAlert(id, falsePositive);
      await refreshDashboard();
      toast(falsePositive ? `${id} ghi nhận là báo động giả` : `Đã đóng ${id}`);
    } catch (error) {
      toast(error instanceof Error ? error.message : "Không đóng được cảnh báo");
    } finally {
      setAlertBusyId(null);
    }
  }

  const openAlerts = alerts.filter((alert) => alert.state === "OPEN").length;
  const liveAlerts = alerts.filter((alert) => alert.state === "OPEN" || alert.state === "ACKNOWLEDGED").length;
  const watching = patients.filter((patient) => patient.status === "WATCH").length;
  const [title, subtitle] = TITLES[view];

  return (
    <>
      <div className="app">
        <Sidebar
          view={view}
          openAlerts={openAlerts}
          patientsTotal={summary?.patients_total ?? patients.length}
          theme={theme}
          onView={setView}
          onTheme={() => setTheme((current) => NEXT_THEME[current])}
        />

        <main className="main">
          <header className="topbar">
            <div>
              <h1>{title}</h1>
              <p className="topbar-meta">
                {view === "dashboard" ? `${patients.length} bệnh nhân đang điều trị · ` : ""}
                {subtitle}
              </p>
            </div>
            <div className="topbar-actions">
              <button
                className="btn sm"
                onClick={() => {
                  refreshDashboard()
                    .then(() => toast("Đã đồng bộ dữ liệu mới nhất"))
                    .catch((error) => toast(error instanceof Error ? error.message : "Không đồng bộ được dữ liệu"));
                }}
              >
                ↻ Làm mới
              </button>
              <span className={`pill ${liveAlerts ? "crit" : "ok"}`}>
                <span className="dot" />
                {liveAlerts} Red Alert
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
              <KpiRow summary={summary} />
              <PatientTable patients={patients} onOpen={openPatient} />
              <GuardBanner title="Ranh giới của AI trong hệ thống này">
                <li>
                  Planning Agent chỉ <b>tính giờ nhắc</b> từ đơn đã được bác sĩ duyệt và lịch sinh hoạt bệnh nhân.
                </li>
                <li>
                  Rescheduling Agent chỉ được <b>dời giờ</b> — không đổi liều, số cữ, đường dùng hay số ngày điều trị.
                </li>
                <li>
                  Xung đột không giải được thì trả <b>NEEDS_REVIEW</b> và giữ nguyên lịch cũ, không tự suy đoán.
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
              patients={patients}
              drugs={drugs}
              patientId={rxPatientId}
              onPatientId={setRxPatientId}
              onToast={toast}
            />
          )}
        </main>
      </div>

      <PatientDrawer
        detail={detail}
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        onPrescribe={(patientId) => {
          setDrawerOpen(false);
          setRxPatientId(patientId);
          setView("rx");
        }}
        onReschedule={() => toast("Đã gửi yêu cầu dời giờ — chỉ thay đổi thời điểm, giữ nguyên liều")}
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
