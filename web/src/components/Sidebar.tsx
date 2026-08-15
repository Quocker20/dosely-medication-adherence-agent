import type { ThemeMode, ViewName } from "../App";
import type { UserResponse } from "../types";

interface Props {
  view: ViewName;
  openAlerts: number;
  patientsTotal: number;
  theme: ThemeMode;
  user: UserResponse | null;
  onView: (view: ViewName) => void;
  onTheme: () => void;
  onLogout: () => void;
}

const THEME_LABEL: Record<ThemeMode, string> = {
  system: "theo hệ thống",
  light: "sáng",
  dark: "tối",
};

export default function Sidebar({
  view,
  openAlerts,
  patientsTotal,
  theme,
  user,
  onView,
  onTheme,
  onLogout,
}: Props) {
  return (
    <aside className="rail">
      <div className="brand">
        <div className="brand-mark">Rx</div>
        <div>
          <div className="brand-name">RemindRx</div>
          <div className="brand-sub">Portal bác sĩ · v1.0</div>
        </div>
      </div>

      <div className="doctor">
        <div className="avatar">{user?.role === "ADMIN" ? "AD" : "BS"}</div>
        <div>
          <div className="doctor-name">{user?.phone ?? "—"}</div>
          <div className="doctor-role">
            {user?.role ?? "—"} · {patientsTotal} bệnh nhân
          </div>
        </div>
      </div>

      <nav>
        <div className="nav-group">
          <div className="eyebrow">Theo dõi</div>
          <button className="nav-item" aria-current={view === "dashboard"} onClick={() => onView("dashboard")}>
            <svg className="ico" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true">
              <rect x="2" y="2" width="5" height="6" rx="1" />
              <rect x="9" y="2" width="5" height="4" rx="1" />
              <rect x="2" y="10" width="5" height="4" rx="1" />
              <rect x="9" y="8" width="5" height="6" rx="1" />
            </svg>
            Dashboard
          </button>
          <button className="nav-item" aria-current={view === "alerts"} onClick={() => onView("alerts")}>
            <svg className="ico" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true">
              <path d="M8 2.5 14.5 13.5h-13z" strokeLinejoin="round" />
              <path d="M8 6.5v3.2M8 11.6v.1" strokeLinecap="round" />
            </svg>
            Cảnh báo
            {openAlerts > 0 && <span className="count">{openAlerts}</span>}
          </button>
        </div>

        <div className="nav-group">
          <div className="eyebrow">Điều trị</div>
          <button className="nav-item" aria-current={view === "rx"} onClick={() => onView("rx")}>
            <svg className="ico" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true">
              <rect x="2" y="4" width="12" height="10" rx="2" />
              <path d="M5 4V2.8h6V4M5.5 8h5M5.5 11h3" strokeLinecap="round" />
            </svg>
            Kê đơn thuốc
          </button>
        </div>
      </nav>

      <div className="rail-foot">
        <button className="theme-toggle" onClick={onTheme}>
          <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" width="14" height="14" aria-hidden="true">
            <circle cx="8" cy="8" r="3.2" />
            <path
              d="M8 1v1.6M8 13.4V15M15 8h-1.6M2.6 8H1M12.9 3.1l-1.1 1.1M4.2 11.8l-1.1 1.1M12.9 12.9l-1.1-1.1M4.2 4.2 3.1 3.1"
              strokeLinecap="round"
            />
          </svg>
          <span>Giao diện: {THEME_LABEL[theme]}</span>
        </button>
        <button className="btn ghost sm" style={{ width: "100%" }} onClick={onLogout}>
          Đăng xuất
        </button>
        <p className="rail-note">Mọi thay đổi phác đồ đều cần bác sĩ duyệt (HITL).</p>
      </div>
    </aside>
  );
}
