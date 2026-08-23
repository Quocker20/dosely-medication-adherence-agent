import { useCallback, useEffect, useState } from "react";

import { api } from "../../../api";
import type { DashboardPatientListItem, DoctorDetail } from "../../../types";
import { ErrorPanel, errorLines } from "./ErrorPanel";

export default function AdminOverview({ toast }: { toast: (message: string) => void }) {
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
