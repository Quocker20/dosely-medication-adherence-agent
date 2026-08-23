import { THEME_LABEL, type ThemeMode } from "../../../hooks/useTheme";
import type { AdminView } from "../AdminPortal";

export default function AdminSidebar({
  view,
  theme,
  onView,
  onTheme,
  onLogout,
}: {
  view: AdminView;
  theme: ThemeMode;
  onView: (view: AdminView) => void;
  onTheme: () => void;
  onLogout: () => void;
}) {
  return (
    <aside className="rail">
      <div className="brand">
        <div className="brand-mark">Rx</div>
        <div><div className="brand-name">RemindRx</div><div className="brand-sub">Admin console · v1.0</div></div>
      </div>
      <div className="doctor">
        <div className="avatar">AD</div>
        <div><div className="doctor-name">Quản trị hệ thống</div><div className="doctor-role">ADMIN · toàn hệ thống</div></div>
      </div>
      <nav>
        <div className="nav-group">
          <div className="eyebrow">Quản trị</div>
          <button className="nav-item" aria-current={view === "overview"} onClick={() => onView("overview")}>▦ Tổng quan</button>
          <button className="nav-item" aria-current={view === "doctors"} onClick={() => onView("doctors")}>♙ Quản lý doctor</button>
          <button className="nav-item" aria-current={view === "audit"} onClick={() => onView("audit")}>◷ Audit logs</button>
        </div>
      </nav>
      <div className="rail-foot">
        <button className="theme-toggle" onClick={onTheme}>◐ <span>Giao diện: {THEME_LABEL[theme]}</span></button>
        <button className="btn ghost sm" style={{ width: "100%" }} onClick={onLogout}>Đăng xuất</button>
        <p className="rail-note">Admin chỉ quản trị tài khoản và theo dõi hệ thống; thay đổi phác đồ thuộc doctor.</p>
      </div>
    </aside>
  );
}
