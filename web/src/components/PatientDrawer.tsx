import { useEffect, useRef } from "react";

import {
  adherenceTone,
  alertSeverityView,
  alertStatusView,
  alertTriggerLabel,
  formatDateTime,
  patientDisplayName,
} from "../lib/labels";
import type { ActiveSchedule, DashboardPatientDetail, PatientRoutine } from "../types";

interface Props {
  detail: DashboardPatientDetail | null;
  routine: PatientRoutine | null;
  schedule: ActiveSchedule | null;
  open: boolean;
  busy: boolean;
  onClose: () => void;
  onPrescribe: (phone: string) => void;
  onReschedule: (patientId: string) => void;
}

/** "HH:MM:SS" -> "HH:MM"; null khi bệnh nhân chưa onboarding. */
function shortTime(value: string | null): string {
  if (!value) return "—";
  return value.slice(0, 5);
}

export function RoutinePills({ routine }: { routine: PatientRoutine | null }) {
  if (!routine) {
    return <p className="rail-note">Bệnh nhân chưa khai báo lịch sinh hoạt.</p>;
  }

  const entries: [string, string | null][] = [
    ["Thức dậy", routine.wake_time],
    ["Ăn sáng", routine.breakfast_time],
    ["Ăn trưa", routine.lunch_time],
    ["Ăn tối", routine.dinner_time],
    ["Đi ngủ", routine.sleep_time],
  ];

  return (
    <div className="routine">
      {entries.map(([label, time]) => (
        <span className="pill" key={label}>
          {label} <b>{shortTime(time)}</b>
        </span>
      ))}
    </div>
  );
}

export default function PatientDrawer({
  detail,
  routine,
  schedule,
  open,
  busy,
  onClose,
  onPrescribe,
  onReschedule,
}: Props) {
  const closeRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (open) closeRef.current?.focus();
  }, [open, detail?.patient.user_id]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  const patient = detail?.patient;
  const adherence = detail?.adherence_summary;

  return (
    <>
      <div className={`scrim ${open ? "open" : ""}`} onClick={onClose} />
      <aside className={`drawer ${open ? "open" : ""}`} aria-hidden={!open} aria-label="Hồ sơ bệnh nhân">
        <div className="drawer-head">
          <div style={{ minWidth: 0 }}>
            <h2>{patient ? patientDisplayName(patient.name) : "—"}</h2>
            <p className="topbar-meta">
              {patient ? `${patient.phone} · mã BN ${patient.user_id.slice(0, 8)}` : ""}
            </p>
          </div>
          <button ref={closeRef} className="btn ghost sm" style={{ marginLeft: "auto" }} onClick={onClose}>
            Đóng ✕
          </button>
        </div>

        {detail && patient && adherence && (
          <div className="drawer-body">
            <div className="drawer-sec">
              <div className="routine">
                <span className={`pill ${adherenceTone(adherence.adherence_rate)}`}>
                  <span className="dot" />
                  Tuân thủ {Math.round(adherence.adherence_rate)}%
                </span>
                <span className="pill mono">{adherence.window_days} ngày gần nhất</span>
                <span className="pill mono">{detail.active_prescriptions_count} đơn đang hiệu lực</span>
              </div>
            </div>

            <div className="drawer-sec">
              <div className="eyebrow">Thống kê liều (cửa sổ {adherence.window_days} ngày)</div>
              <div className="routine">
                <span className="pill mono">Tổng {adherence.total_doses}</span>
                <span className="pill ok">Đã uống {adherence.taken_doses}</span>
                <span className="pill warn">Bỏ qua {adherence.skipped_doses}</span>
                <span className="pill crit">Không phản hồi {adherence.missed_doses}</span>
              </div>
            </div>

            <div className="drawer-sec">
              <div className="eyebrow">Lịch sinh hoạt (đầu vào Planning Agent)</div>
              <RoutinePills routine={routine} />
            </div>

            <div className="drawer-sec">
              <div className="eyebrow">Lịch uống hôm nay</div>
              {!schedule || schedule.doses.length === 0 ? (
                <p className="rail-note">
                  Chưa có cữ nào hôm nay. Lịch chỉ sinh sau khi có đơn APPROVED và Planning Agent chạy xong.
                </p>
              ) : (
                <div className="log">
                  {schedule.doses.map((dose) => (
                    <div className="log-row" key={dose.scheduled_dose_id}>
                      <div className="log-time">{formatDateTime(dose.current_scheduled_at)}</div>
                      <div
                        className={`log-what ${
                          dose.status === "MISSED" || dose.status === "SKIPPED"
                            ? "miss"
                            : dose.status === "LATE"
                              ? "late"
                              : ""
                        }`}
                      >
                        {dose.medication_name} · {dose.status}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            <div className="drawer-sec">
              <div className="eyebrow">Cảnh báo gần đây</div>
              {detail.recent_alerts.length === 0 ? (
                <p className="rail-note">Không có cảnh báo nào gần đây.</p>
              ) : (
                <div className="log">
                  {detail.recent_alerts.map((alert) => {
                    const statusView = alertStatusView(alert.status);
                    const severityView = alertSeverityView(alert.severity);
                    return (
                      <div className="log-row" key={alert.id}>
                        <div className="log-time">{formatDateTime(alert.created_at)}</div>
                        <div className="log-what">
                          {alertTriggerLabel(alert.triggered_by_type)}
                          {" · "}
                          <span style={{ color: `var(--${severityView.tone})` }}>{severityView.label}</span>
                          {" · "}
                          <span style={{ color: `var(--${statusView.tone})` }}>{statusView.label}</span>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>

            <div className="drawer-sec">
              <div className="row-actions">
                <button className="btn primary" onClick={() => onPrescribe(patient.phone)}>
                  Kê đơn cho bệnh nhân này
                </button>
                <button className="btn" disabled={busy} onClick={() => onReschedule(patient.user_id)}>
                  {busy ? "Đang gửi…" : "Yêu cầu Rescheduling Agent dời giờ"}
                </button>
              </div>
              <p className="rail-note">
                Nút dời giờ chỉ tính lại thời điểm nhắc. Muốn đổi liều hay số cữ thì phải tạo đơn mới và duyệt lại.
              </p>
            </div>
          </div>
        )}
      </aside>
    </>
  );
}
