import { useCallback, useEffect, useState, type FormEvent } from "react";

import { ApiError, api } from "../../api";
import { formatDateTime } from "../../lib/labels";
import { setSession, type Session } from "../../session";
import type {
  AuditLog,
  DashboardPatientListItem,
  DoctorDetail,
  PageResponse,
} from "../../types";

type AdminView = "overview" | "doctors" | "audit";
type ThemeMode = "system" | "light" | "dark";

const NEXT_THEME: Record<ThemeMode, ThemeMode> = { system: "light", light: "dark", dark: "system" };
const THEME_LABEL: Record<ThemeMode, string> = { system: "theo hệ thống", light: "sáng", dark: "tối" };

interface Props {
  session: Session;
}

interface DoctorForm {
  phone: string;
  name: string;
  license_no: string;
  specialty: string;
  status: "ACTIVE" | "INACTIVE";
}

const EMPTY_FORM: DoctorForm = {
  phone: "",
  name: "",
  license_no: "",
  specialty: "",
  status: "ACTIVE",
};

function errorLines(error: unknown): string[] {
  if (error instanceof ApiError) return error.details.length ? error.details : [error.message];
  return [error instanceof Error ? error.message : "Lỗi không xác định"];
}

export default function AdminPortal({ session }: Props) {
  const [view, setView] = useState<AdminView>("overview");
  const [theme, setTheme] = useState<ThemeMode>("system");
  const [toasts, setToasts] = useState<{ id: number; text: string }[]>([]);

  const toast = useCallback((text: string) => {
    const id = Date.now() + Math.random();
    setToasts((current) => [...current, { id, text }]);
    window.setTimeout(() => setToasts((current) => current.filter((item) => item.id !== id)), 2800);
  }, []);

  useEffect(() => {
    const root = document.documentElement;
    if (theme === "system") root.removeAttribute("data-theme");
    else root.setAttribute("data-theme", theme);
  }, [theme]);

  async function logout() {
    try {
      await api.logout(session.refreshToken);
    } catch {
      // Session cục bộ vẫn phải bị xóa khi token server đã hết hạn.
    } finally {
      setSession(null);
    }
  }

  const title: Record<AdminView, [string, string]> = {
    overview: ["Tổng quan hệ thống", "Theo dõi tổng thể bệnh nhân, cảnh báo và đội ngũ doctor"],
    doctors: ["Quản lý doctor", "Tạo, cập nhật và vô hiệu hóa tài khoản doctor"],
    audit: ["Audit logs", "Lịch sử thay đổi quản trị do backend ghi nhận"],
  };

  return (
    <>
      <div className="app">
        <AdminSidebar view={view} theme={theme} onView={setView} onTheme={() => setTheme((current) => NEXT_THEME[current])} onLogout={logout} />
        <main className="main">
          <header className="topbar">
            <div>
              <h1>{title[view][0]}</h1>
              <p className="topbar-meta">{title[view][1]}</p>
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

function AdminSidebar({
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

function AdminOverview({ toast }: { toast: (message: string) => void }) {
  const [patients, setPatients] = useState<DashboardPatientListItem[]>([]);
  const [alerts, setAlerts] = useState<{ status: string; severity: string }[]>([]);
  const [doctors, setDoctors] = useState<DoctorDetail[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string[] | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [patientPage, alertPage, doctorPage] = await Promise.all([
        api.dashboardPatients({ page: 1, size: 100 }),
        api.alerts({ page: 1, size: 100 }),
        api.adminDoctors({ page: 1, size: 100 }),
      ]);
      setPatients(patientPage.content);
      setAlerts(alertPage.content);
      setDoctors(doctorPage.content);
    } catch (cause) {
      setError(errorLines(cause));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load().catch(() => undefined); }, [load]);

  const openAlerts = alerts.filter((alert) => alert.status === "OPEN" || alert.status === "ACKNOWLEDGED").length;
  const activeDoctors = doctors.filter((doctor) => doctor.status === "ACTIVE").length;
  const averageAdherence = patients.length
    ? patients.reduce((sum, patient) => sum + patient.adherence_rate, 0) / patients.length
    : 0;

  return (
    <section className="view">
      {error && <ErrorPanel lines={error} onRetry={() => load().catch(() => undefined)} />}
      <div className="kpi-row">
        <div className="card kpi"><span className="kpi-label">Bệnh nhân</span><span className="kpi-value">{loading ? "—" : patients.length}</span><span className="kpi-foot">Tổng trong roster</span></div>
        <div className="card kpi"><span className="kpi-label">Doctor active</span><span className="kpi-value">{loading ? "—" : activeDoctors}</span><span className="kpi-foot">{doctors.length} doctor đã đăng ký</span></div>
        <div className="card kpi is-crit"><span className="kpi-label">Cảnh báo chưa đóng</span><span className="kpi-value">{loading ? "—" : openAlerts}</span><span className="kpi-foot">OPEN + ACKNOWLEDGED</span></div>
        <div className="card kpi is-ok"><span className="kpi-label">Tuân thủ trung bình</span><span className="kpi-value">{loading ? "—" : `${averageAdherence.toFixed(1)}%`}</span><span className="kpi-foot">Từ dashboard backend</span></div>
      </div>
      <div className="card">
        <div className="card-head"><h2>Ưu tiên theo dõi</h2><div className="spacer" /><button className="btn sm" onClick={() => load().then(() => toast("Đã đồng bộ tổng quan")).catch(() => undefined)}>↻ Làm mới</button></div>
        <div className="card-body">
          {patients.length === 0 && !loading ? <p className="empty">Chưa có bệnh nhân trong dashboard.</p> : <div className="table-wrap"><table><thead><tr><th>Bệnh nhân</th><th>Tuân thủ</th><th>Cảnh báo</th><th>Khảo sát cuối</th></tr></thead><tbody>{patients.slice(0, 10).map((patient) => <tr key={patient.patient_id}><td>{patient.patient_name}</td><td><span className={`pill ${patient.adherence_rate < 70 ? "crit" : patient.adherence_rate < 85 ? "warn" : "ok"}`}>{patient.adherence_rate.toFixed(1)}%</span></td><td>{patient.open_alerts_count}</td><td>{patient.last_survey_date ?? "—"}</td></tr>)}</tbody></table></div>}
        </div>
      </div>
    </section>
  );
}

function DoctorManagement({ toast }: { toast: (message: string) => void }) {
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [data, setData] = useState<PageResponse<DoctorDetail> | null>(null);
  const [form, setForm] = useState<DoctorForm>(EMPTY_FORM);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [tempPassword, setTempPassword] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string[] | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try { setData(await api.adminDoctors({ page, size: 10, search })); }
    catch (cause) { setError(errorLines(cause)); }
  }, [page, search]);
  useEffect(() => { load().catch(() => undefined); }, [load]);

  function startEdit(doctor: DoctorDetail) {
    setEditingId(doctor.user_id);
    setTempPassword(null);
    setForm({ phone: doctor.phone, name: doctor.name, license_no: doctor.license_no, specialty: doctor.specialty ?? "", status: doctor.status === "INACTIVE" ? "INACTIVE" : "ACTIVE" });
  }

  function resetForm(clearTempPassword = true) {
    setEditingId(null);
    setForm(EMPTY_FORM);
    if (clearTempPassword) setTempPassword(null);
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true); setError(null);
    try {
      if (editingId) {
        await api.updateDoctor(editingId, { name: form.name.trim(), specialty: form.specialty.trim() || null, status: form.status });
        toast("Đã cập nhật doctor");
        resetForm();
      } else {
        const created = await api.createDoctor({ phone: form.phone.trim(), name: form.name.trim(), license_no: form.license_no.trim(), specialty: form.specialty.trim() || null });
        setTempPassword(created.temp_password);
        toast("Đã tạo doctor; temporary PIN chỉ hiển thị lần này");
        resetForm(false);
      }
      await load();
    } catch (cause) { setError(errorLines(cause)); }
    finally { setBusy(false); }
  }

  async function deactivate(doctor: DoctorDetail) {
    if (!window.confirm(`Vô hiệu hóa tài khoản doctor ${doctor.name}?`)) return;
    setBusy(true); setError(null);
    try { await api.deactivateDoctor(doctor.user_id); toast("Đã vô hiệu hóa doctor"); await load(); }
    catch (cause) { setError(errorLines(cause)); }
    finally { setBusy(false); }
  }

  return (
    <section className="view">
      {error && <ErrorPanel lines={error} onRetry={() => load().catch(() => undefined)} />}
      {tempPassword && <div className="errors"><b>Temporary PIN của doctor mới</b><p className="mono">{tempPassword}</p><span>Hãy sao chép và gửi bảo mật; backend chỉ trả giá trị này trong response tạo tài khoản.</span></div>}
      <div className="admin-two-col">
        <form className="card" onSubmit={submit}>
          <div className="card-head"><h2>{editingId ? "Sửa doctor" : "Tạo doctor mới"}</h2><div className="spacer" />{editingId && <button type="button" className="btn ghost sm" onClick={() => resetForm()}>Hủy sửa</button>}</div>
          <div className="card-body">
            {!editingId && <label>Số điện thoại<input required pattern="^\\+?[0-9]{9,15}$" value={form.phone} onChange={(event) => setForm({ ...form, phone: event.target.value })} placeholder="+84901234567" /></label>}
            <label>Họ tên<input required value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} /></label>
            {!editingId && <label>License number<input required value={form.license_no} onChange={(event) => setForm({ ...form, license_no: event.target.value })} /></label>}
            {editingId && <label>Trạng thái<select value={form.status} onChange={(event) => setForm({ ...form, status: event.target.value as DoctorForm["status"] })}><option value="ACTIVE">ACTIVE</option><option value="INACTIVE">INACTIVE</option></select></label>}
            <label>Chuyên khoa<input value={form.specialty} onChange={(event) => setForm({ ...form, specialty: event.target.value })} placeholder="Nội tổng quát" /></label>
            <div className="row-actions"><button className="btn primary" disabled={busy} type="submit">{busy ? "Đang lưu…" : editingId ? "Lưu thay đổi" : "Tạo doctor"}</button></div>
          </div>
        </form>
        <div className="card">
          <div className="card-head"><h2>Danh sách doctor</h2></div>
          <div className="card-body">
            <div className="admin-toolbar"><input aria-label="Tìm doctor" value={search} placeholder="Tên / SĐT / license" onChange={(event) => { setPage(1); setSearch(event.target.value); }} /><button className="btn sm" onClick={() => load().catch(() => undefined)}>Tìm</button></div>
            <div className="table-wrap"><table><thead><tr><th>Doctor</th><th>License</th><th>Chuyên khoa</th><th>Trạng thái</th><th /></tr></thead><tbody>{data?.content.map((doctor) => <tr key={doctor.user_id}><td><b>{doctor.name}</b><br /><span className="rail-note">{doctor.phone}</span></td><td className="mono">{doctor.license_no}</td><td>{doctor.specialty ?? "—"}</td><td><span className={`pill ${doctor.status === "ACTIVE" ? "ok" : "crit"}`}>{doctor.status}</span></td><td><div className="row-actions"><button className="btn sm" onClick={() => startEdit(doctor)}>Sửa</button>{doctor.status === "ACTIVE" && <button className="btn sm" disabled={busy} onClick={() => deactivate(doctor)}>Vô hiệu hóa</button>}</div></td></tr>)}</tbody></table></div>
            {data && data.content.length === 0 && <p className="empty">Không tìm thấy doctor.</p>}
            {data && <div className="row-actions pagination"><button className="btn sm" disabled={page <= 1} onClick={() => setPage((value) => value - 1)}>← Trước</button><span className="rail-note">Trang {page} / {Math.max(data.total_pages, 1)}</span><button className="btn sm" disabled={data.last} onClick={() => setPage((value) => value + 1)}>Sau →</button></div>}
          </div>
        </div>
      </div>
    </section>
  );
}

function AuditLogsView({ toast }: { toast: (message: string) => void }) {
  const [page, setPage] = useState(1);
  const [actorId, setActorId] = useState("");
  const [entityType, setEntityType] = useState("");
  const [data, setData] = useState<PageResponse<AuditLog> | null>(null);
  const [error, setError] = useState<string[] | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try { setData(await api.adminAuditLogs({ page, size: 20, actorId: actorId.trim() || undefined, entityType: entityType.trim() || undefined })); }
    catch (cause) { setError(errorLines(cause)); }
  }, [actorId, entityType, page]);
  useEffect(() => { load().catch(() => undefined); }, [load]);

  return (
    <section className="view">
      {error && <ErrorPanel lines={error} onRetry={() => load().catch(() => undefined)} />}
      <div className="card">
        <div className="card-head"><h2>Audit logs</h2><div className="spacer" /><button className="btn sm" onClick={() => load().then(() => toast("Đã tải audit logs")).catch(() => undefined)}>↻ Làm mới</button></div>
        <div className="card-body">
          <div className="admin-toolbar"><input placeholder="Actor UUID" value={actorId} onChange={(event) => { setPage(1); setActorId(event.target.value); }} /><input placeholder="Entity type, ví dụ DOCTOR_PROFILE" value={entityType} onChange={(event) => { setPage(1); setEntityType(event.target.value); }} /><button className="btn sm" onClick={() => load().catch(() => undefined)}>Lọc</button></div>
          <div className="table-wrap"><table><thead><tr><th>Thời gian</th><th>Action</th><th>Entity</th><th>Actor</th><th>IP</th><th>Chi tiết</th></tr></thead><tbody>{data?.content.map((log) => <tr key={log.id}><td>{formatDateTime(log.created_at)}</td><td><span className="pill accent">{log.action}</span></td><td>{log.entity_type}<br /><span className="rail-note">{log.entity_id ?? "—"}</span></td><td className="mono">{log.actor_user_id ?? "—"}</td><td>{log.ip_address ?? "—"}</td><td><details><summary>Xem JSON</summary><pre className="admin-json">{JSON.stringify({ old_values: log.old_values, new_values: log.new_values }, null, 2)}</pre></details></td></tr>)}</tbody></table></div>
          {data && data.content.length === 0 && <p className="empty">Chưa có audit log phù hợp.</p>}
          {data && <div className="row-actions pagination"><button className="btn sm" disabled={page <= 1} onClick={() => setPage((value) => value - 1)}>← Trước</button><span className="rail-note">Trang {page} / {Math.max(data.total_pages, 1)}</span><button className="btn sm" disabled={data.last} onClick={() => setPage((value) => value + 1)}>Sau →</button></div>}
        </div>
      </div>
    </section>
  );
}

function ErrorPanel({ lines, onRetry }: { lines: string[]; onRetry: () => void }) {
  return <div className="errors"><b>Không tải được dữ liệu</b><ul>{lines.map((line, index) => <li key={index}>{line}</li>)}</ul><div><button className="btn sm" onClick={onRetry}>Thử lại</button></div></div>;
}
