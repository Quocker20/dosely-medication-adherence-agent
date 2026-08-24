import { useCallback, useEffect, useState, type FormEvent } from "react";

import { api } from "../../../api";
import type { DoctorDetail, PageResponse } from "../../../types";
import { ErrorPanel, errorLines } from "./ErrorPanel";

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

export default function DoctorManagement({ toast }: { toast: (message: string) => void }) {
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
