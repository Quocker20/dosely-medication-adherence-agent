import { adherenceTone, formatDate, initialsOf, patientDisplayName, patientPriority } from "../lib/labels";
import type { DashboardPatientListItem } from "../types";

interface Props {
  patients: DashboardPatientListItem[];
  onOpen: (patientId: string) => void;
}

export default function PatientTable({ patients, onOpen }: Props) {
  return (
    <div className="card">
      <div className="card-head">
        <h2>Bệnh nhân theo mức ưu tiên</h2>
        <span className="pill mono">GET /dashboard/patients</span>
        <div className="spacer" />
        <span style={{ fontSize: 12.5, color: "var(--text-2)" }}>Bấm một dòng để mở hồ sơ</span>
      </div>

      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Bệnh nhân</th>
              <th>Tuân thủ</th>
              <th>Cảnh báo đang mở</th>
              <th>Khảo sát gần nhất</th>
              <th>Trạng thái</th>
            </tr>
          </thead>
          <tbody>
            {patients.map((patient) => {
              const priority = patientPriority(patient.open_alerts_count, patient.adherence_rate);
              const tone = adherenceTone(patient.adherence_rate);
              return (
                <tr
                  key={patient.patient_id}
                  className={priority.row}
                  tabIndex={0}
                  role="button"
                  aria-label={`Mở hồ sơ ${patientDisplayName(patient.patient_name)}`}
                  onClick={() => onOpen(patient.patient_id)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();
                      onOpen(patient.patient_id);
                    }
                  }}
                >
                  <td>
                    <div className="who">
                      <div className="avatar">{initialsOf(patient.patient_name)}</div>
                      <div>
                        <div className="who-name">{patientDisplayName(patient.patient_name)}</div>
                        <div className="who-meta mono">{patient.patient_id.slice(0, 8)}</div>
                      </div>
                    </div>
                  </td>
                  <td>
                    <div className="adh">
                      <div className="adh-num" style={{ color: `var(--${tone})` }}>
                        {Math.round(patient.adherence_rate)}%
                      </div>
                    </div>
                  </td>
                  <td>
                    <div className="cell-note">
                      {patient.open_alerts_count > 0 ? (
                        <strong style={{ color: "var(--crit)" }}>{patient.open_alerts_count} cảnh báo</strong>
                      ) : (
                        "—"
                      )}
                    </div>
                  </td>
                  <td>
                    <div className="cell-note">{formatDate(patient.last_survey_date)}</div>
                  </td>
                  <td>
                    <span className={`pill ${priority.tone}`}>
                      <span className="dot" />
                      {priority.label}
                    </span>
                  </td>
                </tr>
              );
            })}

            {patients.length === 0 && (
              <tr>
                <td colSpan={5}>
                  <p className="empty">
                    Chưa có bệnh nhân nào trong phạm vi của bạn.
                    <br />
                    Bác sĩ chỉ thấy bệnh nhân mình đã kê ít nhất một đơn.
                  </p>
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <div className="legend">
        <span>
          <i style={{ background: "var(--crit)" }} />
          Cần xử lý: có cảnh báo đang mở (OPEN hoặc ACKNOWLEDGED)
        </span>
        <span>
          <i style={{ background: "var(--warn)" }} />
          Theo dõi: tuân thủ &lt; 70%
        </span>
        <span>
          <i style={{ background: "var(--ok)" }} />
          Ổn định
        </span>
      </div>
    </div>
  );
}
