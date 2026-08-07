import { Fragment, useEffect, useRef } from "react";

import { doseCell, PATIENT_STATUS } from "../lib/labels";
import type { PatientDetail, PatientRoutine } from "../types";

interface Props {
  detail: PatientDetail | null;
  open: boolean;
  onClose: () => void;
  onPrescribe: (patientId: string) => void;
  onReschedule: (patientId: string) => void;
}

const DAYS = ["T2", "T3", "T4", "T5", "T6", "T7", "CN"];

export function RoutinePills({ routine }: { routine: PatientRoutine }) {
  const entries: [string, string][] = [
    ["Thức dậy", routine.wake],
    ["Ăn sáng", routine.breakfast],
    ["Ăn trưa", routine.lunch],
    ["Ăn tối", routine.dinner],
    ["Đi ngủ", routine.sleep],
  ];
  return (
    <div className="routine">
      {entries.map(([label, time]) => (
        <span className="pill" key={label}>
          {label} <b>{time}</b>
        </span>
      ))}
    </div>
  );
}

export default function PatientDrawer({ detail, open, onClose, onPrescribe, onReschedule }: Props) {
  const closeRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (open) closeRef.current?.focus();
  }, [open, detail?.patient.id]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  const patient = detail?.patient;
  const rows = detail ? [...new Set(detail.week.map((cell) => cell.row))] : [];

  return (
    <>
      <div className={`scrim ${open ? "open" : ""}`} onClick={onClose} />
      <aside className={`drawer ${open ? "open" : ""}`} aria-hidden={!open} aria-label="Hồ sơ bệnh nhân">
        <div className="drawer-head">
          <div style={{ minWidth: 0 }}>
            <h2>{patient?.name ?? "—"}</h2>
            <p className="topbar-meta">
              {patient ? `${patient.age} tuổi · ${patient.diagnosis} · mã BN ${patient.id.toUpperCase()}` : ""}
            </p>
          </div>
          <button ref={closeRef} className="btn ghost sm" style={{ marginLeft: "auto" }} onClick={onClose}>
            Đóng ✕
          </button>
        </div>

        {detail && patient && (
          <div className="drawer-body">
            <div className="drawer-sec">
              <div className="routine">
                <span className={`pill ${PATIENT_STATUS[patient.status].tone}`}>
                  <span className="dot" />
                  {PATIENT_STATUS[patient.status].label}
                </span>
                <span className="pill mono">Tuân thủ 7 ngày {patient.adherence_rate}%</span>
                <span className="pill mono">Chuỗi bỏ liều: {patient.consecutive_miss}</span>
              </div>
            </div>

            <div className="drawer-sec">
              <div className="eyebrow">Lịch uống 7 ngày gần nhất</div>
              <div className="week">
                <div className="week-h" />
                {DAYS.map((day) => (
                  <div className="week-h" key={day}>
                    {day}
                  </div>
                ))}
                {rows.map((row) => (
                  <Fragment key={row}>
                    <div className="week-t">{row}</div>
                    {detail.week
                      .filter((cell) => cell.row === row)
                      .sort((a, b) => a.day - b.day)
                      .map((cell) => {
                        const view = doseCell(cell.status);
                        return (
                          <div className={`cellbox ${view.cls}`} key={`${row}-${cell.day}`} title={view.title}>
                            {view.glyph}
                          </div>
                        );
                      })}
                  </Fragment>
                ))}
              </div>
              <div className="week-legend">
                <span>✓ đã uống</span>
                <span>~ uống muộn</span>
                <span>✕ bỏ qua / MISSED</span>
              </div>
            </div>

            <div className="drawer-sec">
              <div className="eyebrow">Lịch sinh hoạt (đầu vào Planning Agent)</div>
              <RoutinePills routine={detail.routine} />
            </div>

            <div className="drawer-sec">
              <div className="eyebrow">Nhật ký tuân thủ (append-only)</div>
              <div className="log">
                {detail.logs.map((log, index) => {
                  const tone =
                    log.status === "MISSED" || log.status === "SKIPPED" ? "miss" : log.status === "LATE" ? "late" : "";
                  return (
                    <div className="log-row" key={`${log.at}-${index}`}>
                      <div className="log-time">{log.at}</div>
                      <div className={`log-what ${tone}`}>{log.message}</div>
                    </div>
                  );
                })}
              </div>
            </div>

            <div className="drawer-sec">
              <div className="row-actions">
                <button className="btn primary" onClick={() => onPrescribe(patient.id)}>
                  Kê đơn cho bệnh nhân này
                </button>
                <button className="btn" onClick={() => onReschedule(patient.id)}>
                  Yêu cầu Rescheduling Agent dời giờ
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
