import { adherenceTone, formatDate, initialsOf, patientDisplayName, patientPriority } from "../../../utils/labels";
import type { DashboardPatientListItem } from "../../../types";

interface Props {
  patients: DashboardPatientListItem[];
  onOpen: (patientId: string) => void;
  onRefresh: () => void;
  onAdd: () => void;
  selectedPatientId?: string | null;
}

export default function PatientTable({ patients, onOpen, onRefresh, onAdd, selectedPatientId = null }: Props) {
  return (
    <div className="card">
      <div className="card-head">
        <h2>Bệnh nhân</h2>
        <div className="spacer" />
        <div className="patient-table-actions">
          <span>Bấm một dòng để mở hồ sơ</span>
          <button className="btn" onClick={onRefresh}>↻ Làm mới</button>
          <button className="btn primary" onClick={onAdd}>＋ Thêm bệnh nhân</button>
        </div>
      </div>

      <div className="legend">
        <span>
          <i style={{ background: "var(--crit)" }} />
          Cần xử lý
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
              const isSelected = patient.patient_id === selectedPatientId;
              return (
                <tr
                  key={patient.patient_id}
                  className={`${priority.row} ${isSelected ? "is-selected" : ""}`}
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
                    <span className={`pill flat ${priority.tone}`}>
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
    </div>
  );
}
