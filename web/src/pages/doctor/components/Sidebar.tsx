import { THEME_LABEL, type ThemeMode } from "../../../hooks/useTheme";
import type { UserResponse } from "../../../types";
import type { ViewName } from "../DoctorPortal";

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
          <button className="nav-item" aria-current={view === "patients"} onClick={() => onView("patients")}>
            <svg className="ico" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true">
              <circle cx="6" cy="5" r="2.3" />
              <path d="M2 13c.3-2.6 1.7-4 4-4s3.7 1.4 4 4M10.8 3.5a2.1 2.1 0 0 1 0 4M11.5 9.3c1.5.4 2.3 1.6 2.5 3.7" strokeLinecap="round" />
            </svg>
            Bệnh nhân
            {patientsTotal > 0 && <span className="count muted">{patientsTotal}</span>}
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
        <div className="rail-hitl-card">
          <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
            <path d="M8 1.5 13 3.4v3.9c0 3.2-2 5.8-5 7.2-3-1.4-5-4-5-7.2V3.4z" strokeLinejoin="round" />
            <path d="m5.8 8 1.4 1.4 3-3" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          <div>
            <b>Ràng buộc HITL</b>
            <small>Thay đổi phác đồ cần bác sĩ duyệt.</small>
          </div>
        </div>
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
        <div className="doctor rail-profile">
          <div className="avatar">{user?.role === "ADMIN" ? "AD" : "BS"}</div>
          <div className="rail-profile-copy">
            <div className="doctor-name">Bác sĩ phụ trách</div>
            <div className="doctor-role">{user?.phone ?? "—"} · {patientsTotal} bệnh nhân</div>
          </div>
          <button className="rail-logout" aria-label="Đăng xuất" title="Đăng xuất" onClick={onLogout}>
            <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true">
              <path d="M6.5 2.5H3.8A1.3 1.3 0 0 0 2.5 3.8v8.4a1.3 1.3 0 0 0 1.3 1.3h2.7M9.5 5l3 3-3 3M12.5 8h-7" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </button>
        </div>
      </div>
    </aside>
  );
}
