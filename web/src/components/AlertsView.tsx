import { ALERT_KIND } from "../lib/labels";
import type { Alert, Patient } from "../types";
import GuardBanner from "./GuardBanner";

interface Props {
  alerts: Alert[];
  patients: Patient[];
  busyId: string | null;
  onAcknowledge: (id: string) => void;
  onResolve: (id: string, falsePositive: boolean) => void;
  onOpenPatient: (patientId: string) => void;
}

const FLOW = ["OPEN", "ACKNOWLEDGED", "RESOLVED"] as const;

export default function AlertsView({ alerts, patients, busyId, onAcknowledge, onResolve, onOpenPatient }: Props) {
  const byId = new Map(patients.map((patient) => [patient.id, patient]));

  return (
    <section className="view">
      <GuardBanner title="Closed-loop Red Alert">
        <li>
          Kích hoạt khi <b>3 liều SKIPPED/MISSED liên tiếp</b>, hoặc bệnh nhân bấm <b>SOS</b>, hoặc triệu chứng mức{" "}
          <b>SEVERE</b>.
        </li>
        <li>Gửi đa kênh trong &lt;10 giây tới người thân và portal bác sĩ; retry có backoff, quá ngưỡng vào dead-letter.</li>
        <li>
          Cảnh báo chỉ đóng khi <b>bác sĩ xác nhận</b> — hệ thống không tự resolve.
        </li>
      </GuardBanner>

      <div className="alert-list">
        {alerts.map((alert) => {
          const patient = byId.get(alert.patient_id);
          const done = alert.state === "RESOLVED" || alert.state === "CLOSED_FALSE_POSITIVE";
          const tone = done ? "ok" : alert.state === "ACKNOWLEDGED" ? "warn" : "crit";
          const busy = busyId === alert.id;

          return (
            <article
              key={alert.id}
              className={`alert ${alert.state === "ACKNOWLEDGED" ? "is-ack" : ""} ${done ? "is-done" : ""}`}
            >
              <div className="alert-head">
                <div style={{ minWidth: 0 }}>
                  <div className="alert-title">
                    {alert.title} — {patient?.name ?? alert.patient_id}
                  </div>
                  <div className="alert-sub">
                    {patient ? `${patient.age} tuổi · ${patient.diagnosis} · ` : ""}
                    mở lúc {alert.opened_at} · {alert.id}
                  </div>
                </div>
                <div style={{ marginLeft: "auto", display: "flex", gap: 6, flexWrap: "wrap" }}>
                  <span className="pill mono">{ALERT_KIND[alert.kind]}</span>
                  <span className={`pill ${tone}`}>
                    <span className="dot" />
                    {alert.state}
                  </span>
                </div>
              </div>

              <div className="alert-body">
                <p className="alert-sub">{alert.detail}</p>
                <div className="chan">
                  <span className="chan-item">Đa kênh trong {(alert.dispatch_ms / 1000).toFixed(1)}s:</span>
                  {alert.channels.map((channel) => (
                    <span className="chan-item" key={channel.name}>
                      <span
                        className="chan-dot"
                        style={{ background: `var(--${channel.status === "DELIVERED" ? "ok" : "warn"})` }}
                      />
                      <b>{channel.name}</b> {channel.status}
                    </span>
                  ))}
                </div>
              </div>

              <div className="alert-foot">
                {alert.state === "OPEN" && (
                  <button className="btn sm" disabled={busy} onClick={() => onAcknowledge(alert.id)}>
                    Tôi đã tiếp nhận
                  </button>
                )}
                {alert.state === "ACKNOWLEDGED" && (
                  <>
                    <button className="btn sm primary" disabled={busy} onClick={() => onResolve(alert.id, false)}>
                      Đã xử lý — đóng cảnh báo
                    </button>
                    <button className="btn sm ghost" disabled={busy} onClick={() => onResolve(alert.id, true)}>
                      Báo động giả
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
                      {alert.state === state ? <b>{state}</b> : <span>{state}</span>}
                    </span>
                  ))}
                </div>
              </div>
            </article>
          );
        })}
      </div>
    </section>
  );
}
