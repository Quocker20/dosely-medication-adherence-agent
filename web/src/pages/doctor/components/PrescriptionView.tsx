import { useEffect, useState } from "react";

import { ApiError, api, waitForAgentRun } from "../../../api";
import {
  agentRunStatusView,
  doseStatusLabel,
  formatTime,
  isoDate,
  prescriptionStatusView,
} from "../../../utils/labels";
import type {
  ActiveSchedule,
  AgentRunStatus,
  MedicationDetail,
  PrescriptionDetail,
  PrescriptionItemIn,
} from "../../../types";
import GuardBanner from "../../../components/shared/GuardBanner";
import MedicationCombobox from "./MedicationCombobox";

interface Props {
  phone: string;
  onPhone: (phone: string) => void;
  onToast: (message: string) => void;
  onPrescribed: () => void;
}

const MEAL_RELATIONS: { value: string; label: string }[] = [
  { value: "", label: "Không quy định" },
  { value: "BEFORE_MEAL", label: "Trước ăn" },
  { value: "AFTER_MEAL", label: "Sau ăn" },
  { value: "WITH_MEAL", label: "Trong bữa ăn" },
];

const ROUTES: { value: string; label: string }[] = [
  { value: "ORAL", label: "Đường uống" },
  { value: "INJECTION", label: "Đường tiêm" },
  { value: "TOPICAL", label: "Dùng ngoài da" },
];

const SEXES: { value: PatientForm["sex"]; label: string }[] = [
  { value: "MALE", label: "Nam" },
  { value: "FEMALE", label: "Nữ" },
  { value: "OTHER", label: "Khác" },
];

interface PatientForm {
  name: string;
  dob: string;
  sex: "MALE" | "FEMALE" | "OTHER";
  emergency_note: string;
}

const EMPTY_PATIENT: PatientForm = { name: "", dob: "", sex: "MALE", emergency_note: "" };

/** Ô nào backend đã có dữ liệu thì khoá; ô rỗng vẫn để bác sĩ điền. */
type LockedFields = Partial<Record<keyof PatientForm, boolean>>;

function emptyItem(): PrescriptionItemIn {
  return {
    medication_id: "",
    dose_unit: "Viên",
    morning_dose: 1,
    noon_dose: null,
    evening_dose: null,
    bedtime_dose: null,
    route: "ORAL",
    meal_relation: "AFTER_MEAL",
    minimum_interval_minutes: null,
    start_date: isoDate(new Date()),
    end_date: null,
    instructions: null,
    is_critical: false,
  };
}

/** Ô liều: chuỗi rỗng -> null (backend nhận Decimal | null, không nhận ""). */
function parseDose(raw: string): number | null {
  const trimmed = raw.trim();
  if (trimmed === "") return null;
  const value = Number(trimmed);
  return Number.isFinite(value) ? value : null;
}

function doseValue(dose: number | null): string {
  return dose === null ? "" : String(dose);
}

/**
 * Gợi ý thao tác thân thiện cho bác sĩ theo mã tình huống hệ thống.
 */
function errorHint(code: string): string {
  switch (code) {
    case "ScheduleConstraintError":
      return "Hai cữ của cùng một thuốc gần nhau hơn mức giãn cách tối thiểu. Vui lòng tăng khoảng cách giữa các bữa ăn trong lịch sinh hoạt hoặc giảm bớt số phút tại ô “Giãn cách tối thiểu”.";
    case "PlanningNeedsReviewError":
      return "Dữ liệu chưa đủ để tự động tạo lịch. Vui lòng kiểm tra lại lịch sinh hoạt của bệnh nhân và các cữ thuốc đã ghi nhận.";
    case "MissingRoutineError":
      return "Bệnh nhân chưa khai báo giờ ăn và giờ ngủ nên hệ thống chưa có mốc thời gian sắp xếp cữ thuốc. Bệnh nhân có thể cập nhật trong ứng dụng.";
    case "InvalidPrescriptionTimingError":
      return "Một dòng thuốc có liều lượng hoặc thời gian chưa phù hợp. Vui lòng kiểm tra lại liều và thời gian bắt đầu/kết thúc.";
    default:
      return "Vui lòng kiểm tra lại thông tin đơn thuốc hoặc lịch sinh hoạt rồi thực hiện lại.";
  }
}

function errorCodeTitle(code: string): string {
  switch (code) {
    case "ScheduleConstraintError":
      return "Khoảng cách cữ thuốc chưa phù hợp";
    case "PlanningNeedsReviewError":
      return "Cần kiểm tra lại thông tin";
    case "MissingRoutineError":
      return "Chưa có lịch sinh hoạt";
    case "InvalidPrescriptionTimingError":
      return "Thông số thời gian hoặc liều chưa hợp lệ";
    default:
      return "Cần điều chỉnh thông tin";
  }
}

export default function PrescriptionView({ phone, onPhone, onToast, onPrescribed }: Props) {
  const [medications, setMedications] = useState<MedicationDetail[]>([]);
  const [diagnosis, setDiagnosis] = useState("");
  const [items, setItems] = useState<PrescriptionItemIn[]>([emptyItem()]);
  const [errorDetails, setErrorDetails] = useState<string[]>([]);
  const [prescription, setPrescription] = useState<PrescriptionDetail | null>(null);
  const [tempPassword, setTempPassword] = useState<string | null>(null);
  const [agentRun, setAgentRun] = useState<AgentRunStatus | null>(null);
  const [schedule, setSchedule] = useState<ActiveSchedule | null>(null);
  const [busy, setBusy] = useState(false);

  const [patient, setPatient] = useState<PatientForm>(EMPTY_PATIENT);
  const [locked, setLocked] = useState<LockedFields>({});
  const [lookup, setLookup] = useState<{ state: "idle" | "busy" | "found" | "new"; message: string }>({
    state: "idle",
    message: "",
  });

  useEffect(() => {
    let cancelled = false;
    api
      .medications({ size: 100 })
      .then((page) => {
        if (!cancelled) setMedications(page.content);
      })
      .catch((error) => {
        if (!cancelled) {
          onToast(error instanceof ApiError ? error.message : "Không tải được danh mục thuốc");
        }
      });
    return () => {
      cancelled = true;
    };
  }, [onToast]);

  function patchItem(index: number, patch: Partial<PrescriptionItemIn>) {
    setItems((current) => current.map((item, i) => (i === index ? { ...item, ...patch } : item)));
    setPrescription(null);
    setSchedule(null);
    setAgentRun(null);
  }

  function patchPatient(patch: Partial<PatientForm>) {
    setPatient((current) => ({ ...current, ...patch }));
    setPrescription(null);
    setSchedule(null);
    setAgentRun(null);
  }

  function resetDraft() {
    setItems([emptyItem()]);
    setDiagnosis("");
    setErrorDetails([]);
    setPrescription(null);
    setTempPassword(null);
    setSchedule(null);
    setAgentRun(null);
    setPatient(EMPTY_PATIENT);
    setLocked({});
    setLookup({ state: "idle", message: "" });
    onToast("Đã xóa nháp");
  }

  /**
   * Tra hồ sơ theo số điện thoại trước khi kê.
   *
   * 404 là kết quả hợp lệ, không phải sự cố: bệnh nhân chưa có hồ sơ thì bác sĩ
   * điền tay và POST /prescriptions sẽ tự tạo tài khoản. Chỉ khoá đúng những ô
   * backend trả về có dữ liệu — bệnh nhân tạo tự động từ đơn cũ có dob/sex NULL,
   * khoá luôn ô rỗng sẽ làm form không submit được (name/dob/sex là bắt buộc).
   */
  async function lookupPatient() {
    const trimmedPhone = phone.trim();
    if (!trimmedPhone) {
      onToast("Nhập số điện thoại trước khi kiểm tra");
      return;
    }

    setLookup({ state: "busy", message: "" });
    try {
      const found = await api.patientByPhone(trimmedPhone);
      const hasName = Boolean(found.name?.trim()) && found.name.trim() !== "NULL";
      setPatient({
        name: hasName ? found.name.trim() : "",
        dob: found.dob ?? "",
        sex: (found.sex as PatientForm["sex"]) || "MALE",
        emergency_note: found.emergency_note ?? "",
      });
      setLocked({
        name: hasName,
        dob: Boolean(found.dob),
        sex: Boolean(found.sex),
        emergency_note: Boolean(found.emergency_note),
      });

      const missing = [
        !hasName && "họ tên",
        !found.dob && "ngày sinh",
        !found.sex && "giới tính",
      ].filter(Boolean);
      setLookup({
        state: "found",
        message: missing.length
          ? `Đã có hồ sơ nhưng thiếu ${missing.join(", ")} — điền nốt rồi kê đơn.`
          : "Đã có hồ sơ, thông tin bên dưới lấy từ hệ thống và đã khoá.",
      });
    } catch (error) {
      if (error instanceof ApiError && error.status === 404) {
        setPatient(EMPTY_PATIENT);
        setLocked({});
        setLookup({ state: "new", message: "Chưa có hồ sơ — điền thông tin, hệ thống sẽ tạo tài khoản khi duyệt đơn." });
        return;
      }
      setLookup({ state: "idle", message: "" });
      onToast(error instanceof ApiError ? error.message : "Không tra cứu được bệnh nhân");
    }
  }

  /**
   * Luồng đúng theo contract: tạo DRAFT -> bác sĩ duyệt -> Planning Agent sinh
   * lịch. Generate trả 202 nên phải poll agent run rồi mới đọc được lịch.
   */
  async function approve() {
    const trimmedPhone = phone.trim();
    if (!trimmedPhone) {
      onToast("Nhập số điện thoại bệnh nhân trước");
      return;
    }
    if (items.some((item) => !item.medication_id)) {
      onToast("Mỗi dòng phải chọn một thuốc trong danh mục");
      return;
    }
    // Chặn tại chỗ thay vì để backend trả 422: 3 trường này là bắt buộc trong
    // CreatePrescriptionRequest, báo sớm đỡ mất một vòng gọi mạng.
    if (!patient.name.trim() || !patient.dob || !patient.sex) {
      onToast("Cần đủ họ tên, ngày sinh và giới tính của bệnh nhân");
      return;
    }

    setBusy(true);
    setErrorDetails([]);
    setSchedule(null);
    setAgentRun(null);

    try {
      const created = await api.createPrescription({
        phone: trimmedPhone,
        name: patient.name.trim(),
        dob: patient.dob,
        sex: patient.sex,
        emergency_note: patient.emergency_note.trim() || null,
        diagnosis_note: diagnosis.trim() || null,
        items,
      });
      setTempPassword(created.temp_password);

      const approved = await api.approvePrescription(created.prescription.id);
      setPrescription(approved);
      onPrescribed();

      const dispatched = await api.generateSchedule(approved.patient_id, "Đơn vừa được bác sĩ duyệt");
      const run = await waitForAgentRun(dispatched.agent_run_id);
      setAgentRun(run);

      if (run.status === "COMPLETED") {
        setSchedule(await api.schedule(approved.patient_id, isoDate(new Date())));
        onToast(`Đơn đã duyệt · Hệ thống đã tạo ${run.generated_dose_count ?? 0} cữ nhắc`);
      } else {
        onToast(`Đơn đã duyệt — trạng thái: ${agentRunStatusView(run.status).label}, lịch chưa kích hoạt`);
      }
    } catch (error) {
      if (error instanceof ApiError) {
        setErrorDetails(error.details.length > 0 ? error.details : [error.message]);
        onToast("Chưa duyệt được — kiểm tra thông tin bên dưới form");
      } else {
        onToast(error instanceof Error ? error.message : "Lỗi không xác định");
      }
    } finally {
      setBusy(false);
    }
  }

  /**
   * Tính lại lịch nhắc trên đơn đã duyệt, không tạo đơn mới.
   */
  async function retryScheduling() {
    if (!prescription) return;
    setBusy(true);
    try {
      const dispatched = await api.generateSchedule(prescription.patient_id, "Bác sĩ yêu cầu tính lại lịch nhắc");
      const run = await waitForAgentRun(dispatched.agent_run_id);
      setAgentRun(run);
      if (run.status === "COMPLETED") {
        setSchedule(await api.schedule(prescription.patient_id, isoDate(new Date())));
        onToast(`Đã cập nhật lịch nhắc · ${run.generated_dose_count ?? 0} cữ`);
      } else {
        onToast(`Hệ thống vẫn ở trạng thái: ${agentRunStatusView(run.status).label}`);
      }
    } catch (error) {
      onToast(error instanceof ApiError ? error.message : "Không tính lại được lịch nhắc");
    } finally {
      setBusy(false);
    }
  }

  const rxStatus = prescriptionStatusView(prescription?.status);
  const agentStatus = agentRunStatusView(agentRun?.status);
  const agentTone = agentStatus.tone || "warn";

  return (
    <section className="view">
      <GuardBanner title="Nguyên tắc an toàn y tế khi kê đơn">
        <li>
          Chỉ bác sĩ có thẩm quyền nhập và duyệt đơn. Hệ thống AI <b>không tự kê đơn, không đổi liều, không chỉ định ngưng thuốc</b>.
        </li>
        <li>
          Lịch nhắc uống thuốc chỉ được tự động kích hoạt sau khi đơn thuốc <b>đã được bác sĩ phê duyệt</b>.
        </li>
        <li>
          Tên thuốc và hàm lượng được chuẩn hóa trực tiếp từ danh mục dược để đảm bảo an toàn điều trị.
        </li>
      </GuardBanner>

      <div className="rx-grid">
        <div className="card">
          <div className="card-head">
            <h2>Nhập đơn thuốc điện tử</h2>
            <div className="spacer" />
            <span className={`pill ${rxStatus.tone}`}>
              <span className="dot" />
              {rxStatus.label}
            </span>
          </div>

          <div className="card-body">
            <div className="row-actions" style={{ alignItems: "flex-end" }}>
              <label style={{ flex: "1 1 240px", maxWidth: 340 }}>
                Số điện thoại bệnh nhân
                <input
                  type="tel"
                  placeholder="0901234567"
                  value={phone}
                  onChange={(event) => {
                    onPhone(event.target.value);
                    // Số đổi thì kết quả tra cứu cũ không còn đúng — mở khoá lại.
                    setLocked({});
                    setLookup({ state: "idle", message: "" });
                  }}
                />
              </label>
              <button className="btn" onClick={lookupPatient} disabled={lookup.state === "busy"}>
                {lookup.state === "busy" ? "Đang tra…" : "Kiểm tra"}
              </button>
            </div>

            {lookup.message ? (
              <p className={`rail-note ${lookup.state === "found" ? "lookup-found" : "lookup-new"}`}>
                {lookup.message}
              </p>
            ) : (
              <p className="rail-note">
                Bấm <b>Kiểm tra</b> để lấy sẵn hồ sơ nếu bệnh nhân đã có tài khoản. Chưa có thì hệ thống tự tạo và trả
                mã PIN tạm khi duyệt đơn.
              </p>
            )}

            <div className="rx-fields">
              <label>
                Họ tên bệnh nhân
                <input
                  value={patient.name}
                  readOnly={locked.name}
                  placeholder="Nguyễn Văn A"
                  onChange={(event) => patchPatient({ name: event.target.value })}
                />
              </label>
              <label>
                Ngày sinh
                <input
                  type="date"
                  value={patient.dob}
                  readOnly={locked.dob}
                  max={isoDate(new Date())}
                  onChange={(event) => patchPatient({ dob: event.target.value })}
                />
              </label>
              <label>
                Giới tính
                <select
                  value={patient.sex}
                  disabled={locked.sex}
                  onChange={(event) => patchPatient({ sex: event.target.value as PatientForm["sex"] })}
                >
                  {SEXES.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </label>
              <label className="wide">
                Ghi chú khẩn cấp (không bắt buộc)
                <input
                  value={patient.emergency_note}
                  readOnly={locked.emergency_note}
                  placeholder="vd. dị ứng penicillin, người nhà: 09xx…"
                  onChange={(event) => patchPatient({ emergency_note: event.target.value })}
                />
              </label>
            </div>

            <label>
              Chẩn đoán
              <input
                value={diagnosis}
                placeholder="vd. Tăng huyết áp nguyên phát"
                onChange={(event) => setDiagnosis(event.target.value)}
              />
            </label>

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
                    <div className="wide">
                      <label style={{ marginBottom: 5 }}>Thuốc (danh mục)</label>
                      <MedicationCombobox
                        medications={medications}
                        selectedId={item.medication_id}
                        onSelect={(medication) =>
                          patchItem(index, {
                            medication_id: medication ? medication.id : "",
                          })
                        }
                      />
                    </div>

                    <label>
                      Đơn vị liều
                      <input
                        value={item.dose_unit}
                        onChange={(event) => patchItem(index, { dose_unit: event.target.value })}
                      />
                    </label>

                    <label>
                      Đường dùng
                      <select value={item.route} onChange={(event) => patchItem(index, { route: event.target.value })}>
                        {ROUTES.map((route) => (
                          <option key={route.value} value={route.value}>
                            {route.label}
                          </option>
                        ))}
                      </select>
                    </label>

                    <label>
                      Sáng
                      <input
                        type="number"
                        min={0}
                        step="0.5"
                        value={doseValue(item.morning_dose)}
                        onChange={(event) => patchItem(index, { morning_dose: parseDose(event.target.value) })}
                      />
                    </label>
                    <label>
                      Trưa
                      <input
                        type="number"
                        min={0}
                        step="0.5"
                        value={doseValue(item.noon_dose)}
                        onChange={(event) => patchItem(index, { noon_dose: parseDose(event.target.value) })}
                      />
                    </label>
                    <label>
                      Chiều
                      <input
                        type="number"
                        min={0}
                        step="0.5"
                        value={doseValue(item.evening_dose)}
                        onChange={(event) => patchItem(index, { evening_dose: parseDose(event.target.value) })}
                      />
                    </label>
                    <label>
                      Trước ngủ
                      <input
                        type="number"
                        min={0}
                        step="0.5"
                        value={doseValue(item.bedtime_dose)}
                        onChange={(event) => patchItem(index, { bedtime_dose: parseDose(event.target.value) })}
                      />
                    </label>

                    <label>
                      Quan hệ bữa ăn
                      <select
                        value={item.meal_relation ?? ""}
                        onChange={(event) => patchItem(index, { meal_relation: event.target.value || null })}
                      >
                        {MEAL_RELATIONS.map((relation) => (
                          <option key={relation.value} value={relation.value}>
                            {relation.label}
                          </option>
                        ))}
                      </select>
                    </label>

                    <label>
                      Giãn cách tối thiểu (phút)
                      {/* Để trống = không ràng buộc (DB NULL). Nhập 0 tường minh
                          thì planner từ chối cả đơn, nên chặn từ min=1. */}
                      <input
                        type="number"
                        min={1}
                        step={15}
                        value={item.minimum_interval_minutes ?? ""}
                        onChange={(event) =>
                          patchItem(index, {
                            minimum_interval_minutes: event.target.value === "" ? null : Number(event.target.value),
                          })
                        }
                      />
                    </label>

                    <label>
                      Bắt đầu
                      <input
                        type="date"
                        value={item.start_date}
                        onChange={(event) => patchItem(index, { start_date: event.target.value })}
                      />
                    </label>
                    <label>
                      Kết thúc
                      <input
                        type="date"
                        value={item.end_date ?? ""}
                        onChange={(event) => patchItem(index, { end_date: event.target.value || null })}
                      />
                    </label>

                    <label className="wide">
                      Lưu ý cho bệnh nhân
                      <input
                        value={item.instructions ?? ""}
                        placeholder="vd. không dùng chung với nước bưởi"
                        onChange={(event) => patchItem(index, { instructions: event.target.value || null })}
                      />
                    </label>

                    <label
                      className="wide"
                      style={{
                        display: "flex",
                        flexDirection: "row",
                        alignItems: "center",
                        gap: 10,
                        cursor: "pointer",
                        userSelect: "none",
                      }}
                    >
                      <input
                        type="checkbox"
                        checked={item.is_critical}
                        onChange={(event) => patchItem(index, { is_critical: event.target.checked })}
                        style={{
                          width: 18,
                          height: 18,
                          minWidth: 18,
                          minHeight: 18,
                          cursor: "pointer",
                          accentColor: "var(--accent)",
                        }}
                      />
                      <span>THUỐC NGUY HIỂM / QUAN TRỌNG</span>
                    </label>
                    <small className="wide" style={{ color: "var(--text-2)", marginTop: -4 }}>
                      Đánh dấu thuốc quan trọng để hệ thống gửi cảnh báo ngay nếu bệnh nhân bỏ uống thuốc này liên tiếp.
                    </small>
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

            {errorDetails.length > 0 && (
              <div className="errors">
                <b>Thông tin chưa hợp lệ — vui lòng kiểm tra {errorDetails.length} điểm cần sửa:</b>
                <ul>
                  {errorDetails.map((message, index) => (
                    <li key={index}>{message}</li>
                  ))}
                </ul>
              </div>
            )}

            {tempPassword && (
              <div className="errors">
                <b>Tài khoản bệnh nhân vừa được tạo</b>
                <ul>
                  <li>
                    Mã PIN tạm: <b className="mono">{tempPassword}</b> — đọc cho bệnh nhân ngay, chuỗi này chỉ hiện
                    một lần.
                  </li>
                </ul>
              </div>
            )}

            <div className="approve-bar">
              <button className="btn primary" onClick={approve} disabled={busy}>
                {busy ? "Đang duyệt…" : "✓ Duyệt đơn & tạo lịch"}
              </button>
            </div>
          </div>
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          <div className="card">
            <div className="card-head">
              <h2>Lịch nhắc do hệ thống sinh</h2>
              <div className="spacer" />
              <span className={`pill mono ${agentStatus.tone}`}>
                Trạng thái · {agentStatus.label}
              </span>
            </div>

            <div className="card-body">
              {!agentRun && (
                <p className="empty">
                  Vui lòng duyệt đơn để hệ thống tự động lập lịch nhắc uống thuốc cho bệnh nhân.
                  <br />
                  Lịch nhắc chỉ được kích hoạt sau khi đơn thuốc đã được bác sĩ phê duyệt.
                </p>
              )}

              {agentRun && (
                <>
                  <div className="agent-run">
                    <b style={{ color: `var(--${agentTone})` }}>{agentStatus.label}</b>
                  </div>

                  {agentRun.error_code && (
                    <div className="review-box">
                      <b>
                        {agentRun.status === "NEEDS_REVIEW" ? "Cần bác sĩ xem lại" : "Chưa thể lập lịch tự động"} —{" "}
                        <span>{errorCodeTitle(agentRun.error_code)}</span>
                      </b>
                      {agentRun.error_message && <p className="agent-error-message">{agentRun.error_message}</p>}
                      <p>{errorHint(agentRun.error_code)}</p>
                      <p>Lịch cũ giữ nguyên — hệ thống không tự đoán giờ thay bác sĩ.</p>
                      <div className="row-actions">
                        <button className="btn sm" onClick={retryScheduling} disabled={busy || !prescription}>
                          {busy ? "Đang chạy…" : "↻ Tính lại lịch nhắc"}
                        </button>
                      </div>
                    </div>
                  )}

                  {schedule && schedule.doses.length > 0 && (
                    <div className="timeline">
                      {schedule.doses.map((dose) => (
                        <div className="tl-row" key={dose.scheduled_dose_id}>
                          <div className="tl-time">{formatTime(dose.current_scheduled_at)}</div>
                          <div className="tl-items">
                            <div className="tl-dose">
                              <b>{dose.medication_name}</b>
                              <span>{doseStatusLabel(dose.status)}</span>
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}

                  {schedule && schedule.doses.length === 0 && (
                    <p className="empty">Chưa có cữ thuốc nào trong hôm nay — lịch uống có thể bắt đầu từ ngày tiếp theo.</p>
                  )}

                  <p className="rail-note">
                    Hệ thống chỉ tự động sắp xếp khung giờ nhắc uống thuốc. Liều dùng, số cữ và thời gian điều trị được tuân thủ chính xác theo đơn bác sĩ đã duyệt.
                  </p>
                </>
              )}
            </div>
          </div>

        </div>
      </div>
    </section>
  );
}
