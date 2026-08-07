import { adherenceTone, PATIENT_STATUS } from "../lib/labels";
import type { Patient } from "../types";
import Sparkline from "./Sparkline";

interface Props {
  patients: Patient[];
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
              <th>Tuân thủ 7 ngày</th>
              <th>Liều gần nhất</th>
              <th>Triệu chứng khai báo</th>
              <th>Trạng thái</th>
            </tr>
          </thead>
          <tbody>
            {patients.map((patient) => {
              const status = PATIENT_STATUS[patient.status];
              const tone = adherenceTone(patient.adherence_rate);
              return (
                <tr
                  key={patient.id}
                  className={status.row}
                  tabIndex={0}
                  role="button"
                  aria-label={`Mở hồ sơ ${patient.name}`}
                  onClick={() => onOpen(patient.id)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();
                      onOpen(patient.id);
                    }
                  }}
                >
                  <td>
                    <div className="who">
                      <div className="avatar">{patient.initials}</div>
                      <div>
                        <div className="who-name">{patient.name}</div>
                        <div className="who-meta">
                          {patient.age} tuổi · {patient.diagnosis}
                        </div>
                      </div>
                    </div>
                  </td>
                  <td>
                    <div className="adh">
                      <Sparkline values={patient.adherence_7d} tone={tone} />
                      <div className="adh-num" style={{ color: `var(--${tone})` }}>
                        {patient.adherence_rate}%
                      </div>
                    </div>
                  </td>
                  <td>
                    <div className="cell-note">
                      <strong style={{ color: `var(--${patient.last_event.tone})` }}>{patient.last_event.text}</strong>
                      {` · ${patient.last_event.at}`}
                    </div>
                  </td>
                  <td>
                    <div className="cell-note">{patient.symptom}</div>
                  </td>
                  <td>
                    <span className={`pill ${status.tone}`}>
                      <span className="dot" />
                      {status.label}
                    </span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <div className="legend">
        <span>
          <i style={{ background: "var(--crit)" }} />
          Red Alert: bỏ ≥3 liều liên tiếp hoặc triệu chứng nguy hiểm
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
