import { useCallback, useEffect, useState } from "react";

import { ApiError, api } from "../../api";
import GuardBanner from "../../components/shared/GuardBanner";
import { useTheme } from "../../hooks/useTheme";
import { useToasts } from "../../hooks/useToasts";
import { setSession, type Session } from "../../session";
import type { AlertDetail, DashboardPatientListItem } from "../../types";
import { paginationRange } from "../../utils/labels";
import AlertsView from "./components/AlertsView";
import KpiRow from "./components/KpiRow";
import PatientDetailPage from "./components/PatientDetailPage";
import PatientTable from "./components/PatientTable";
import PrescriptionView from "./components/PrescriptionView";
import Sidebar from "./components/Sidebar";
import SurveyView from "./components/SurveyView";

export type ViewName = "dashboard" | "patients" | "alerts" | "surveys" | "rx";

const TITLES: Record<ViewName, [string, string]> = {
  dashboard: ["Dashboard", "Tổng quan tuân thủ điều trị theo thời gian thực"],
  patients: ["Danh sách bệnh nhân", "Tìm kiếm và theo dõi bệnh nhân đang điều trị"],
  alerts: ["Cảnh báo khẩn", "Closed-loop Red Alert · chỉ bác sĩ được đóng cảnh báo"],
  surveys: ["Khảo sát sức khỏe", "Theo dõi khảo sát theo từng bệnh nhân hoặc tổng hợp"],
  rx: ["Kê đơn thuốc điện tử", "Đơn phải được bác sĩ duyệt trước khi sinh lịch nhắc"],
};

const ALERT_FILTERS: { value: string; label: string }[] = [
  { value: "", label: "Tất cả trạng thái" },
  { value: "OPEN", label: "Đang mở" },
  { value: "ACKNOWLEDGED", label: "Đã tiếp nhận" },
  { value: "RESOLVED", label: "Đã đóng" },
];

const ADHERENCE_FILTERS = [
  { value: "", label: "Mọi mức tuân thủ" },
  { value: "LOW", label: "Tuân thủ dưới 50%" },
  { value: "MEDIUM", label: "Tuân thủ 50–69%" },
  { value: "HIGH", label: "Tuân thủ từ 70%" },
];

interface Props {
  session: Session;
  view: ViewName;
  onViewChange: (view: ViewName) => void;
  patientDetailId: string | null;
  onOpenPatient: (patientId: string) => void;
  onClosePatient: () => void;
}

export default function DoctorPortal({ session, view, onViewChange, patientDetailId, onOpenPatient, onClosePatient }: Props) {
  const { theme, cycleTheme } = useTheme();

  const [patients, setPatients] = useState<DashboardPatientListItem[]>([]);
  const [totalPatients, setTotalPatients] = useState(0);
  const [alerts, setAlerts] = useState<AlertDetail[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [patientSearch, setPatientSearch] = useState("");
  const [debouncedPatientSearch, setDebouncedPatientSearch] = useState("");
  const [alertFilter, setAlertFilter] = useState("");
  const [adherenceFilter, setAdherenceFilter] = useState("");
  const [patientPage, setPatientPage] = useState(1);

  const [rxPhone, setRxPhone] = useState("");
  const [alertBusyId, setAlertBusyId] = useState<string | null>(null);
  // setDoctorName tạm không dùng — nguồn duy nhất (api.myDoctorProfile) đang comment, xem TODO dưới.
  const [doctorName] = useState<string | null>(null);
  const { toasts, notify: toast } = useToasts(2600);

  // Tên bác sĩ không nằm trong token — phải hỏi riêng. Hỏng thì bỏ qua, sidebar
  // tự rơi về nhãn chung; không đáng chặn cả portal vì mỗi cái tên.
  // TODO: api.myDoctorProfile() chưa có backend (GET /doctors/me) lẫn client
  // function — gọi thẳng throw TypeError, crash trắng trang toàn portal (không
  // Error Boundary). Comment tạm tới khi BE xong, nối lại sau.
  // useEffect(() => {
  //   let cancelled = false;
  //   api
  //     .myDoctorProfile()
  //     .then((profile) => {
  //       if (!cancelled) setDoctorName(profile.name);
  //     })
  //     .catch(() => {});
  //   return () => {
  //     cancelled = true;
  //   };
  // }, []);

  const refresh = useCallback(async () => {
    const [patientPageResult, alertPage] = await Promise.all([
      api.dashboardPatients({
        page: patientPage,
        size: 20,
        search: debouncedPatientSearch,
        alertStatus: alertFilter || undefined,
        adherenceBand: adherenceFilter || undefined,
      }),
      api.alerts({ size: 50, status: alertFilter || undefined }),
    ]);
    setPatients(patientPageResult.content);
    setTotalPatients(patientPageResult.total_elements);
    setAlerts(alertPage.content);
  }, [adherenceFilter, alertFilter, debouncedPatientSearch, patientPage]);

  useEffect(() => {
    const timer = window.setTimeout(() => setDebouncedPatientSearch(patientSearch), 300);
    return () => window.clearTimeout(timer);
  }, [patientSearch]);

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
  //
  // Vercel không proxy được WebSocket qua rewrite (chỉ HTTP thường), nên khi
  // deploy tách domain (web ở Vercel, backend ở nơi khác) phải nối thẳng vào
  // backend qua VITE_WS_HOST thay vì same-origin. Để trống thì dùng
  // window.location.host như cũ — đúng cho dev/khi web và backend cùng origin.
  useEffect(() => {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const wsHost = import.meta.env.VITE_WS_HOST || window.location.host;
    const url = `${protocol}//${wsHost}/ws/dashboard?token=${encodeURIComponent(session.accessToken)}`;

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
  const activeFilterCount = Number(Boolean(alertFilter)) + Number(Boolean(adherenceFilter));
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
          doctorName={doctorName}
          onView={onViewChange}
          onTheme={cycleTheme}
          onLogout={logout}
        />

        <main className="main">
          {patientDetailId ? (
            <PatientDetailPage
              patientId={patientDetailId}
              accessToken={session.accessToken}
              onBack={onClosePatient}
              onPrescribe={(phone) => {
                setRxPhone(phone);
                onClosePatient();
                onViewChange("rx");
              }}
              onToast={toast}
            />
          ) : <>
          <header className="topbar">
            <div>
              <h1>{title}</h1>
              <p className="topbar-meta">
                {subtitle}
              </p>
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

          {view === "patients" && (
            <section className="view">
              <div className="dashboard-toolbar">
                <div className="search-box">
                  <svg className="ico" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true">
                    <circle cx="6.8" cy="6.8" r="4.3" />
                    <path d="M10.2 10.2 14 14" strokeLinecap="round" />
                  </svg>
                  <input
                    aria-label="Tìm bệnh nhân"
                    placeholder="Tìm bệnh nhân / SĐT"
                    value={patientSearch}
                    onChange={(event) => {
                      setPatientPage(1);
                      setPatientSearch(event.target.value);
                    }}
                  />
                </div>
                <details className="dashboard-filter">
                  <summary>
                    <span aria-hidden="true">☷</span> Bộ lọc
                    {activeFilterCount > 0 && <em>{activeFilterCount}</em>}
                  </summary>
                  <div className="dashboard-filter-menu">
                    <label>
                      <span>Trạng thái cảnh báo</span>
                      <select
                        aria-label="Lọc cảnh báo"
                        value={alertFilter}
                        onChange={(event) => {
                          setPatientPage(1);
                          setAlertFilter(event.target.value);
                        }}
                      >
                        {ALERT_FILTERS.map((filter) => <option key={filter.value} value={filter.value}>{filter.label}</option>)}
                      </select>
                    </label>
                    <label>
                      <span>Mức tuân thủ</span>
                      <select
                        aria-label="Lọc theo mức tuân thủ"
                        value={adherenceFilter}
                        onChange={(event) => {
                          setPatientPage(1);
                          setAdherenceFilter(event.target.value);
                        }}
                      >
                        {ADHERENCE_FILTERS.map((filter) => <option key={filter.value} value={filter.value}>{filter.label}</option>)}
                      </select>
                    </label>
                    <div className="dashboard-filter-actions">
                      <button
                        type="button"
                        className="btn sm"
                        disabled={activeFilterCount === 0}
                        onClick={() => {
                          setPatientPage(1);
                          setAlertFilter("");
                          setAdherenceFilter("");
                        }}
                      >
                        Đặt lại
                      </button>
                      <button
                        type="button"
                        className="btn primary sm"
                        onClick={(event) => event.currentTarget.closest("details")?.removeAttribute("open")}
                      >
                        Xong
                      </button>
                    </div>
                  </div>
                </details>
                <span className={`pill ${liveAlerts ? "crit" : "ok"}`}>
                  <span className="dot" />
                  {liveAlerts} cảnh báo chưa xong
                </span>
                <span className="pill warn">
                  <span className="dot" />
                  {watching} cần theo dõi
                </span>
              </div>
              <PatientTable
                patients={patients}
                onOpen={onOpenPatient}
                onRefresh={() => {
                  refresh()
                    .then(() => toast("Đã đồng bộ dữ liệu mới nhất"))
                    .catch((error) =>
                      toast(error instanceof ApiError ? error.message : "Không đồng bộ được dữ liệu"),
                    );
                }}
                onAdd={() => {
                  setRxPhone("");
                  onViewChange("rx");
                }}
                selectedPatientId={null}
              />
              <nav className="row-actions pager" aria-label="Phân trang bệnh nhân">
                <button
                  className="pager-btn"
                  disabled={patientPage <= 1}
                  onClick={() => setPatientPage((page) => page - 1)}
                >
                  ← Trước
                </button>
                {paginationRange(patientPage, Math.max(1, Math.ceil(totalPatients / 20))).map((item, index) =>
                  item === "ellipsis" ? (
                    <span key={`ellip-${index}`} className="pager-ellip">
                      …
                    </span>
                  ) : (
                    <button
                      key={item}
                      className={`pager-btn ${item === patientPage ? "active" : ""}`}
                      aria-current={item === patientPage}
                      onClick={() => setPatientPage(item)}
                    >
                      {item}
                    </button>
                  ),
                )}
                <button
                  className="pager-btn"
                  disabled={totalPatients <= patientPage * 20}
                  onClick={() => setPatientPage((page) => page + 1)}
                >
                  Sau →
                </button>
              </nav>
            </section>
          )}

          {view === "alerts" && (
            <AlertsView
              alerts={alerts}
              patients={patients}
              busyId={alertBusyId}
              onAcknowledge={acknowledgeAlert}
              onResolve={resolveAlert}
              onOpenPatient={onOpenPatient}
            />
          )}

          {view === "surveys" && (
            <SurveyView patients={patients} onOpenPatient={onOpenPatient} onToast={toast} />
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
          </>}
        </main>
      </div>

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
