import { useState } from "react";

import {
  alertSeverityView,
  alertStatusView,
  alertTriggerLabel,
  alertTypeLabel,
  formatAlertMessage,
  formatDateTime,
  patientDisplayName,
} from "../../../utils/labels";
import type { AlertDetail, DashboardPatientListItem, SuspectedAdverseEvent } from "../../../types";
import GuardBanner from "../../../components/shared/GuardBanner";

interface Props {
  alerts: AlertDetail[];
  adverseEvents: SuspectedAdverseEvent[];
  patients: DashboardPatientListItem[];
  busyId: string | null;
  onAcknowledge: (id: string) => void;
  onResolve: (id: string, resolutionNote: string) => void;
  onOpenPatient: (patientId: string) => void;
  onReviewAdverseEvent: (id: string, causality: string, note: string) => void;
}

const FLOW = ["OPEN", "ACKNOWLEDGED", "RESOLVED"] as const;

export default function AlertsView({
  alerts,
  adverseEvents,
  patients,
  busyId,
  onAcknowledge,
  onResolve,
  onOpenPatient,
  onReviewAdverseEvent,
}: Props) {
  const byId = new Map(patients.map((patient) => [patient.patient_id, patient]));

  // Backend yêu cầu resolution_note không rỗng khi đóng cảnh báo.
  const [notes, setNotes] = useState<Record<string, string>>({});
  const [causalities, setCausalities] = useState<Record<string, string>>({});

  return (
    <section className="view">
      <GuardBanner title="Quy trình xử lý cảnh báo khẩn cấp">
        <li>
          Kích hoạt khi bệnh nhân <b>bỏ liều liên tiếp</b>, bấm <b>SOS</b>, hoặc hệ thống phát hiện <b>triệu chứng nặng</b>.
        </li>
        <li>
          Cảnh báo chỉ được đóng khi <b>bác sĩ xác nhận</b> kèm ghi chú xử lý — hệ thống không tự ý đóng cảnh báo.
        </li>
        <li>
          Trạng thái <b>Đang mở</b> và <b>Đã tiếp nhận</b> đều được tính là chưa hoàn tất: tiếp nhận chỉ ghi nhận đã xem, bác sĩ cần xử lý và nhập ghi chú để đóng cảnh báo.
        </li>
      </GuardBanner>

      <section className="adverse-events-card">
        <div className="adverse-events-head"><div><h2>Triệu chứng/tác dụng không mong muốn nghi ngờ</h2><p>Do bệnh nhân mô tả trong chat; chưa khẳng định thuốc là nguyên nhân.</p></div><span className="pill warn">{adverseEvents.filter((item) => item.review_status !== "REVIEWED").length} chưa đánh giá</span></div>
        <div className="table-wrap"><table className="adverse-events-table"><thead><tr><th>Bệnh nhân</th><th>Triệu chứng</th><th>Bối cảnh thuốc</th><th>Nguy cơ</th><th>Thời điểm</th><th>Đánh giá</th></tr></thead><tbody>
          {adverseEvents.map((event) => <tr key={event.id}>
            <td><button className="link-button" onClick={() => onOpenPatient(event.patient_id)}>{event.patient_name || event.patient_id}</button></td>
            <td><b>{event.symptoms.map((item) => item.name).join(", ")}</b><small className="adverse-raw">“{event.raw_text}”</small></td>
            <td><b>Đã dùng gần thời điểm:</b><small className="adverse-raw">{event.related_medications.filter((item) => item.context_type === "RECENTLY_TAKEN").map((item) => item.drug_name).join(", ") || "Chưa ghi nhận"}</small><b className="adverse-medication-heading">Đơn đang hiệu lực:</b><small className="adverse-raw">{event.related_medications.filter((item) => item.context_type === "ACTIVE_PRESCRIPTION").map((item) => item.drug_name).join(", ") || "Chưa lấy được dữ liệu"}</small></td>
            <td><span className={`pill ${event.risk_level === "CRITICAL" || event.risk_level === "HIGH" ? "crit" : "warn"}`}>{event.risk_level}</span></td>
            <td>{formatDateTime(event.reported_at)}</td>
            <td>{event.review_status === "REVIEWED" ? <><b>{event.causality}</b><small className="adverse-raw">{event.clinician_note}</small></> : <div className="adverse-review"><select value={causalities[event.id] ?? "UNASSESSED"} onChange={(e) => setCausalities((v) => ({ ...v, [event.id]: e.target.value }))}><option value="UNASSESSED">Chưa xác định</option><option value="POSSIBLE">Có thể liên quan</option><option value="UNLIKELY">Ít khả năng liên quan</option><option value="CONFIRMED">Đã xác nhận</option></select><input placeholder="Ghi chú chuyên môn" value={notes[event.id] ?? ""} onChange={(e) => setNotes((v) => ({ ...v, [event.id]: e.target.value }))}/><button className="btn sm" disabled={busyId === event.id || !(notes[event.id] ?? "").trim()} onClick={() => onReviewAdverseEvent(event.id, causalities[event.id] ?? "UNASSESSED", (notes[event.id] ?? "").trim())}>Lưu</button></div>}</td>
          </tr>)}
          {adverseEvents.length === 0 && <tr><td colSpan={6} className="empty">Chưa có triệu chứng nghi ngờ nào được ghi nhận từ chat.</td></tr>}
        </tbody></table></div>
      </section>

      <div className="alert-list">
        {alerts.map((alert) => {
          const patient = byId.get(alert.patient_id);
          const statusView = alertStatusView(alert.status);
          const severityView = alertSeverityView(alert.severity);
          const done = alert.status === "RESOLVED";
          const busy = busyId === alert.id;
          const note = notes[alert.id] ?? "";

          return (
            <article
              key={alert.id}
              className={`alert ${alert.status === "ACKNOWLEDGED" ? "is-ack" : ""} ${done ? "is-done" : ""}`}
            >
              <div className="alert-head">
                <div style={{ minWidth: 0 }}>
                  <div className="alert-title">
                    {alertTriggerLabel(alert.triggered_by_type)} —{" "}
                    {patientDisplayName(alert.patient_name ?? patient?.patient_name ?? null)}
                  </div>
                  <div className="alert-sub">
                    Phát hiện lúc {formatDateTime(alert.created_at)}
                  </div>
                </div>
                <div style={{ marginLeft: "auto", display: "flex", gap: 6, flexWrap: "wrap" }}>
                  <span className="pill mono">{alertTypeLabel(alert.alert_type)}</span>
                  <span className={`pill ${severityView.tone}`}>{severityView.label}</span>
                  <span className={`pill ${statusView.tone}`}>
                    <span className="dot" />
                    {statusView.label}
                  </span>
                </div>
              </div>

              <div className="alert-body">
                {alert.triggered_by_type === "ADHERENCE_REVIEW" ? (
                  <div className="chan" style={{ alignItems: "flex-start", gap: 8 }}>
                    <span className="pill accent" style={{ padding: "1px 6px", fontSize: "11px", flexShrink: 0 }}>
                      Hệ thống phân tích
                    </span>
                    <p style={{ margin: 0, fontSize: "13px", color: "var(--text)" }}>
                      {formatAlertMessage(alert.message)}
                    </p>
                  </div>
                ) : (
                  <p className="alert-sub" style={{ color: "var(--text)", fontSize: "13px" }}>
                    {formatAlertMessage(alert.message)}
                  </p>
                )}
              </div>

              <div className="alert-foot">
                {alert.status === "OPEN" && (
                  <button className="btn sm" disabled={busy} onClick={() => onAcknowledge(alert.id)}>
                    Tôi đã tiếp nhận
                  </button>
                )}

                {alert.status === "ACKNOWLEDGED" && (
                  <>
                    <input
                      className="resolve-note"
                      placeholder="Ghi chú xử lý (bắt buộc)"
                      value={note}
                      onChange={(event) =>
                        setNotes((current) => ({ ...current, [alert.id]: event.target.value }))
                      }
                    />
                    <button
                      className="btn sm primary"
                      disabled={busy || note.trim().length === 0}
                      onClick={() => onResolve(alert.id, note.trim())}
                    >
                      Đã xử lý — đóng cảnh báo
                    </button>
                  </>
                )}

                <button className="btn sm" onClick={() => onOpenPatient(alert.patient_id)}>
                  Mở hồ sơ bệnh nhân
                </button>

                <div className="state-flow">
                  {FLOW.map((state, index) => {
                    const stView = alertStatusView(state);
                    return (
                      <span key={state}>
                        {index > 0 && <span> · </span>}
                        {alert.status === state ? <b>{stView.label}</b> : <span>{stView.label}</span>}
                      </span>
                    );
                  })}
                </div>
              </div>
            </article>
          );
        })}

        {alerts.length === 0 && <p className="empty">Không có cảnh báo nào.</p>}
      </div>
    </section>
  );
}
