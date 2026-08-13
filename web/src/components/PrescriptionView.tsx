import { useEffect, useState } from "react";

import { ApiError, api } from "../api";
import { TIMING_LABEL, TIMINGS } from "../lib/labels";
import type {
  DrugCatalogEntry,
  MedicationSchedule,
  Patient,
  Prescription,
  PrescriptionItemIn,
  ValidationIssue,
} from "../types";
import GuardBanner from "./GuardBanner";
import { RoutinePills } from "./PatientDrawer";

interface Props {
  patients: Patient[];
  drugs: DrugCatalogEntry[];
  patientId: string;
  onPatientId: (id: string) => void;
  onToast: (message: string) => void;
}

function emptyItem(): PrescriptionItemIn {
  return {
    drug_name: "",
    dose_per_intake: "1 viên",
    frequency_per_day: 1,
    timing: "AFTER_BREAKFAST",
    treatment_days: 30,
    patient_note: "",
  };
}

const SEED_ITEMS: PrescriptionItemIn[] = [
  {
    drug_name: "Amlodipin 5mg",
    dose_per_intake: "1 viên",
    frequency_per_day: 1,
    timing: "AFTER_BREAKFAST",
    treatment_days: 30,
    patient_note: "Không dùng chung với nước bưởi",
  },
  {
    drug_name: "Losartan 50mg",
    dose_per_intake: "1 viên",
    frequency_per_day: 2,
    timing: "AFTER_BREAKFAST",
    treatment_days: 30,
    patient_note: "",
  },
];

export default function PrescriptionView({ patients, drugs, patientId, onPatientId, onToast }: Props) {
  const [items, setItems] = useState<PrescriptionItemIn[]>(SEED_ITEMS);
  const [issues, setIssues] = useState<ValidationIssue[]>([]);
  const [prescription, setPrescription] = useState<Prescription | null>(null);
  const [schedule, setSchedule] = useState<MedicationSchedule | null>(null);
  const [busy, setBusy] = useState(false);

  const patient = patients.find((p) => p.id === patientId) ?? patients[0];

  // Đổi bệnh nhân là đổi ngữ cảnh lâm sàng — bỏ kết quả duyệt của bệnh nhân trước.
  useEffect(() => {
    setPrescription(null);
    setSchedule(null);
    setIssues([]);
  }, [patientId]);

  function patchItem(index: number, patch: Partial<PrescriptionItemIn>) {
    setItems((current) => current.map((item, i) => (i === index ? { ...item, ...patch } : item)));
    setPrescription(null);
    setSchedule(null);
  }

  function resetDraft() {
    setItems([emptyItem()]);
    setIssues([]);
    setPrescription(null);
    setSchedule(null);
    onToast("Đã xóa nháp");
  }

  async function approve() {
    if (!patient) return;
    setBusy(true);
    setIssues([]);

    try {
      const draft = await api.createPrescription(patient.id, items);
      const approved = await api.approvePrescription(draft.id);
      setPrescription(approved);

      const generated = await api.generateSchedule(patient.id, draft.id);
      setSchedule(generated);
      onToast(
        generated.status === "ACTIVE"
          ? `Đơn ${approved.id} đã duyệt · lịch nhắc đã kích hoạt`
          : `Đơn ${approved.id} đã duyệt — lịch cần bác sĩ xem lại`,
      );
    } catch (error) {
      if (error instanceof ApiError && error.issues.length > 0) {
        setIssues(error.issues);
        onToast("Chưa duyệt được — kiểm tra lỗi bên dưới form");
      } else {
        onToast(error instanceof Error ? error.message : "Lỗi không xác định");
      }
    } finally {
      setBusy(false);
    }
  }

  const scheduleTone =
    schedule?.status === "ACTIVE" ? "ok" : schedule?.status === "NEEDS_REVIEW" ? "warn" : schedule ? "crit" : "";

  return (
    <section className="view">
      <GuardBanner title="HITL bắt buộc — bác sĩ là người duyệt cuối cùng">
        <li>
          Chỉ bác sĩ nhập và duyệt đơn. AI <b>không kê đơn, không đổi liều, không khuyên ngưng thuốc</b>.
        </li>
        <li>
          Đơn ở trạng thái <b>DRAFT</b> không sinh lịch nhắc. Chỉ khi <b>APPROVED</b> Planning Agent mới chạy.
        </li>
        <li>Nếu bật OCR ảnh đơn: kết quả chỉ điền sẵn ô nhập, bác sĩ vẫn phải rà soát trước khi duyệt.</li>
      </GuardBanner>

      <div className="rx-grid">
        <div className="card">
          <div className="card-head">
            <h2>Nhập đơn thuốc điện tử</h2>
            <div className="spacer" />
            <span className={`pill ${prescription ? "ok" : ""}`}>
              <span className="dot" />
              {prescription ? `${prescription.status} · ${prescription.id}` : "Nháp · chờ duyệt"}
            </span>
          </div>

          <div className="card-body">
            <label style={{ maxWidth: 340 }}>
              Bệnh nhân
              <select value={patient?.id ?? ""} onChange={(event) => onPatientId(event.target.value)}>
                {patients.map((option) => (
                  <option key={option.id} value={option.id}>
                    {option.name} · {option.age} tuổi · {option.diagnosis}
                  </option>
                ))}
              </select>
            </label>

            {patient && (
              <div className="drawer-sec">
                <div className="eyebrow">Lịch sinh hoạt dùng làm đầu vào cho Planning Agent</div>
                <RoutinePills routine={patient.routine} />
              </div>
            )}

            <datalist id="drug-catalog">
              {drugs.map((drug) => (
                <option key={drug.drug_id} value={drug.brand_name} />
              ))}
            </datalist>

            <div className="rx-stack">
              {items.map((item, index) => (
                <div className="rx-item" key={index}>
                  <div className="rx-item-head">
                    <span className="idx">Thuốc {String(index + 1).padStart(2, "0")}</span>
                    {items.length > 1 && (
                      <button
                        className="btn ghost sm"
                        style={{ marginLeft: "auto" }}
                        onClick={() => setItems((current) => current.filter((_, i) => i !== index))}
                      >
                        Xóa
                      </button>
                    )}
                  </div>

                  <div className="rx-fields">
                    <label className="wide">
                      Thuốc
                      <input
                        list="drug-catalog"
                        value={item.drug_name}
                        placeholder="Gõ để tìm trong danh mục dược phẩm"
                        onChange={(event) => patchItem(index, { drug_name: event.target.value })}
                      />
                    </label>
                    <label>
                      Liều / lần
                      <input
                        value={item.dose_per_intake}
                        onChange={(event) => patchItem(index, { dose_per_intake: event.target.value })}
                      />
                    </label>
                    <label>
                      Số lần / ngày
                      <input
                        type="number"
                        min={1}
                        max={6}
                        value={item.frequency_per_day}
                        onChange={(event) => patchItem(index, { frequency_per_day: Number(event.target.value) })}
                      />
                    </label>
                    <label>
                      Thời điểm
                      <select
                        value={item.timing}
                        onChange={(event) => patchItem(index, { timing: event.target.value as PrescriptionItemIn["timing"] })}
                      >
                        {TIMINGS.map((timing) => (
                          <option key={timing} value={timing}>
                            {TIMING_LABEL[timing]}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label>
                      Số ngày
                      <input
                        type="number"
                        min={1}
                        max={365}
                        value={item.treatment_days}
                        onChange={(event) => patchItem(index, { treatment_days: Number(event.target.value) })}
                      />
                    </label>
                    <label className="wide">
                      Lưu ý cho bệnh nhân
                      <input
                        value={item.patient_note}
                        placeholder="vd. không dùng chung với nước bưởi"
                        onChange={(event) => patchItem(index, { patient_note: event.target.value })}
                      />
                    </label>
                  </div>
                </div>
              ))}
            </div>

            <div className="row-actions">
              <button className="btn" onClick={() => setItems((current) => [...current, emptyItem()])}>
                + Thêm thuốc
              </button>
              <button className="btn ghost" onClick={resetDraft}>
                Xóa nháp
              </button>
            </div>

            {issues.length > 0 && (
              <div className="errors">
                <b>Validator chặn duyệt — {issues.length} lỗi cần sửa</b>
                <ul>
                  {issues.map((issue, index) => (
                    <li key={`${issue.code}-${index}`}>{issue.message}</li>
                  ))}
                </ul>
              </div>
            )}

            <div className="approve-bar">
              <button className="btn primary" onClick={approve} disabled={busy}>
                {busy ? "Đang duyệt…" : "✓ Duyệt đơn & tạo lịch"}
              </button>
              <span style={{ fontSize: 12, color: "var(--text-2)" }}>Ký duyệt bởi BS. Nguyễn Văn A</span>
            </div>
          </div>
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          <div className="card">
            <div className="card-head">
              <h2>Lịch nhắc do Planning Agent sinh</h2>
              <div className="spacer" />
              <span className={`pill mono ${scheduleTone}`}>SCHEDULE · {schedule?.status ?? "chưa tạo"}</span>
            </div>

            <div className="card-body">
              {!schedule && (
                <p className="empty">
                  Duyệt đơn để Planning Agent tính khung giờ nhắc.
                  <br />
                  Không có đơn APPROVED thì không có lịch — đúng theo guardrail.
                </p>
              )}

              {schedule && (
                <>
                  <div className="agent-run">
                    <span>Planning Agent ·</span>
                    <span className="num">{schedule.agent_run.id}</span>
                    <span>· GENERATING →</span>
                    <b style={{ color: `var(--${scheduleTone})` }}>{schedule.status}</b>
                    <span>·</span>
                    <span className="num">{schedule.agent_run.latency_ms} ms</span>
                    <span>(SLO &lt; 10.000 ms)</span>
                  </div>

                  {schedule.slots.length === 0 ? (
                    <p className="empty">Không có cữ nào được tạo — toàn bộ đơn chờ bác sĩ xem lại.</p>
                  ) : (
                    <div className="timeline">
                      {schedule.slots.map((slot) => (
                        <div className="tl-row" key={slot.time}>
                          <div className="tl-time">{slot.time}</div>
                          <div className="tl-items">
                            {slot.doses.map((dose, index) => (
                              <div className="tl-dose" key={`${dose.drug_name}-${index}`}>
                                <b>{dose.drug_name}</b>
                                <span>
                                  {dose.dose_per_intake} · {dose.treatment_days} ngày
                                  {dose.patient_note ? ` · ${dose.patient_note}` : ""}
                                </span>
                              </div>
                            ))}
                          </div>
                        </div>
                      ))}
                    </div>
                  )}

                  {schedule.review_notes.length > 0 && (
                    <div className="review-box">
                      <b>{schedule.status} — agent dừng lại, không tự suy đoán</b>
                      {schedule.review_notes.map((note, index) => (
                        <p key={index}>{note}</p>
                      ))}
                      <p>Lịch cũ giữ nguyên. Bác sĩ sửa thời điểm hoặc số cữ rồi duyệt lại.</p>
                    </div>
                  )}

                  <p className="rail-note">
                    Agent chỉ sinh khung giờ. Liều, số cữ, số ngày lấy nguyên từ đơn bác sĩ đã duyệt.
                  </p>
                </>
              )}
            </div>
          </div>

          <div className="card">
            <div className="card-head">
              <h2>JSON chuẩn hóa gửi cho agent</h2>
              <div className="spacer" />
              <span className="pill mono">POST /prescriptions/{"{id}"}/approve</span>
            </div>
            <div className="card-body">
              <pre>
                {prescription
                  ? JSON.stringify(
                      {
                        ...prescription,
                        routine_snapshot: patient?.routine,
                        schedule_status: schedule?.status ?? null,
                        agent_scope: schedule?.agent_run.scope ?? [],
                        agent_denied_ops: schedule?.agent_run.denied_ops ?? [],
                      },
                      null,
                      2,
                    )
                  : "// Chưa có đơn được duyệt."}
              </pre>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
