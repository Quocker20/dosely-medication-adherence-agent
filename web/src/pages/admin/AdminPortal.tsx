import { useState } from "react";

import { api } from "../../api";
import { useTheme } from "../../hooks/useTheme";
import { useToasts } from "../../hooks/useToasts";
import { setSession, type Session } from "../../session";
import AdminOverview from "./components/AdminOverview";
import AdminSidebar from "./components/AdminSidebar";
import AuditLogsView from "./components/AuditLogsView";
import DoctorManagement from "./components/DoctorManagement";

export type AdminView = "overview" | "doctors" | "audit";

interface Props {
  session: Session;
}

const TITLES: Record<AdminView, [string, string]> = {
  overview: ["Tổng quan hệ thống", "Theo dõi tổng thể bệnh nhân, cảnh báo và đội ngũ doctor"],
  doctors: ["Quản lý doctor", "Tạo, cập nhật và vô hiệu hóa tài khoản doctor"],
  audit: ["Audit logs", "Lịch sử thay đổi quản trị do backend ghi nhận"],
};

export default function AdminPortal({ session }: Props) {
  const [view, setView] = useState<AdminView>("overview");
  const { theme, cycleTheme } = useTheme();
  const { toasts, notify: toast } = useToasts();

  async function logout() {
    try {
      await api.logout(session.refreshToken);
    } catch {
      // Session cục bộ vẫn phải bị xóa khi token server đã hết hạn.
    } finally {
      setSession(null);
    }
  }

  return (
    <>
      <div className="app">
        <AdminSidebar view={view} theme={theme} onView={setView} onTheme={cycleTheme} onLogout={logout} />
        <main className="main">
          <header className="topbar">
            <div>
              <h1>{TITLES[view][0]}</h1>
              <p className="topbar-meta">{TITLES[view][1]}</p>
            </div>
            <div className="topbar-actions">
              <span className="pill accent"><span className="dot" />ADMIN · {session.user.phone}</span>
            </div>
          </header>
          {view === "overview" && <AdminOverview toast={toast} />}
          {view === "doctors" && <DoctorManagement toast={toast} />}
          {view === "audit" && <AuditLogsView toast={toast} />}
        </main>
      </div>
      <div className="toast-wrap">
        {toasts.map((item) => <div className="toast" key={item.id}>{item.text}</div>)}
      </div>
    </>
  );
}
