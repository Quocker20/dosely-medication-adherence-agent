import { useState } from "react";

import {
  alertSeverityView,
  alertStatusView,
  alertTriggerLabel,
  formatDateTime,
  patientDisplayName,
} from "../../../utils/labels";
import type { AlertDetail, DashboardPatientListItem } from "../../../types";
import GuardBanner from "../../../components/shared/GuardBanner";

interface Props {
  alerts: AlertDetail[];
  patients: DashboardPatientListItem[];
  busyId: string | null;
  onAcknowledge: (id: string) => void;
  onResolve: (id: string, resolutionNote: string) => void;
  onOpenPatient: (patientId: string) => void;
}

const FLOW = ["OPEN", "ACKNOWLEDGED", "RESOLVED"] as const;

export default function AlertsView({
  alerts,
  patients,
  busyId,
  onAcknowledge,
  onResolve,
  onOpenPatient,
}: Props) {
  const byId = new Map(patients.map((patient) => [patient.patient_id, patient]));

  // Backend đòi resolution_note không rỗng, nên phải nhập trước khi đóng.
  const [notes, setNotes] = useState<Record<string, string>>({});

  return (
    <section className="view">
      <GuardBanner title="Closed-loop Red Alert">
        <li>
          Kích hoạt khi <b>bỏ liều liên tiếp</b>, bệnh nhân bấm <b>SOS</b>, hoặc agent phát hiện <b>triệu chứng nặng</b>.
        </li>
        <li>
          Cảnh báo chỉ đóng khi <b>bác sĩ xác nhận</b> kèm ghi chú xử lý — hệ thống không tự resolve.
        </li>
        <li>
          Dashboard đếm cả <b>OPEN</b> và <b>ACKNOWLEDGED</b> là chưa xong: đã xem không có nghĩa đã xử lý.
        </li>
      </GuardBanner>

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
                    mở lúc {formatDateTime(alert.created_at)} · <span className="mono">{alert.id.slice(0, 8)}</span>
                  </div>
                </div>
                <div style={{ marginLeft: "auto", display: "flex", gap: 6, flexWrap: "wrap" }}>
                  <span className="pill mono">{alert.alert_type}</span>
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
                      AI
                    </span>
                    <p style={{ margin: 0, fontSize: "13px", color: "var(--text)" }}>
                      {alert.message ?? "Không có mô tả kèm theo."}
                    </p>
                  </div>
                ) : (
                  <p className="alert-sub">{alert.message ?? "Không có mô tả kèm theo."}</p>
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

                <button className="btn sm ghost" onClick={() => onOpenPatient(alert.patient_id)}>
                  Mở hồ sơ bệnh nhân
                </button>

                <div className="state-flow">
                  {FLOW.map((state, index) => (
                    <span key={state}>
                      {index > 0 && <span> · </span>}
                      {alert.status === state ? <b>{state}</b> : <span>{state}</span>}
                    </span>
                  ))}
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
