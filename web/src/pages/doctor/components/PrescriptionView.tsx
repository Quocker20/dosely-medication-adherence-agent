import { useEffect, useState } from "react";

import { ApiError, api, waitForAgentRun } from "../../../api";
import { formatTime, isoDate } from "../../../utils/labels";
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

const ROUTES = ["ORAL", "INJECTION", "TOPICAL"];

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
    dose_unit: "viên",
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
 * Gợi ý thao tác theo error_code của agent run.
 *
 * error_code là tên class exception phía backend (src/modules/agents/planner.py),
 * bản thân nó không nói bác sĩ phải sửa gì — bảng này dịch sang việc cần làm.
 */
function errorHint(code: string): string {
  switch (code) {
    case "ScheduleConstraintError":
      return "Hai cữ của cùng một thuốc gần nhau hơn mức giãn cách tối thiểu. Tăng khoảng cách giữa các bữa trong lịch sinh hoạt bệnh nhân, hoặc giảm/bỏ trống ô “Giãn cách tối thiểu” của thuốc bị nêu ở trên.";
    case "PlanningNeedsReviewError":
      return "Dữ liệu đầu vào không đủ chắc để agent tự lập lịch. Kiểm tra lịch sinh hoạt của bệnh nhân và các cữ đã ghi nhận trước đó.";
    case "MissingRoutineError":
      return "Bệnh nhân chưa khai báo giờ ăn/ngủ nên agent không có mốc để neo cữ thuốc. Nhờ bệnh nhân cập nhật lịch sinh hoạt trong app.";
    case "InvalidPrescriptionTimingError":
      return "Một dòng thuốc có liều ≤ 0, không có cữ nào, hoặc “Giãn cách tối thiểu” nhập số ≤ 0. Muốn không ràng buộc giãn cách thì để trống ô đó thay vì điền 0.";
    default:
      return "Xem thông báo phía trên để biết chi tiết; sửa đơn hoặc lịch sinh hoạt rồi chạy lại.";
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
        onToast(`Đơn đã duyệt · Planning Agent sinh ${run.generated_dose_count ?? 0} cữ`);
      } else {
        onToast(`Đơn đã duyệt — agent trả trạng thái ${run.status}, lịch chưa kích hoạt`);
      }
    } catch (error) {
      if (error instanceof ApiError) {
        setErrorDetails(error.details.length > 0 ? error.details : [error.message]);
        onToast("Chưa duyệt được — kiểm tra lỗi bên dưới form");
      } else {
        onToast(error instanceof Error ? error.message : "Lỗi không xác định");
      }
    } finally {
      setBusy(false);
    }
  }

  /**
   * Chạy lại Planning Agent trên đơn đã duyệt, không tạo đơn mới.
   *
   * Đơn APPROVED bị đóng băng theo HITL nên không sửa được ở đây — nút này dành
   * cho trường hợp nguyên nhân nằm ngoài đơn (lịch sinh hoạt bệnh nhân vừa được
   * cập nhật), sửa xong thì chạy lại là ra lịch.
   */
  async function retryScheduling() {
    if (!prescription) return;
    setBusy(true);
    try {
      const dispatched = await api.generateSchedule(prescription.patient_id, "Bác sĩ chạy lại sau khi xem lỗi");
      const run = await waitForAgentRun(dispatched.agent_run_id);
      setAgentRun(run);
      if (run.status === "COMPLETED") {
        setSchedule(await api.schedule(prescription.patient_id, isoDate(new Date())));
        onToast(`Đã sinh lịch · ${run.generated_dose_count ?? 0} cữ`);
      } else {
        onToast(`Agent vẫn dừng ở trạng thái ${run.status}`);
      }
    } catch (error) {
      onToast(error instanceof ApiError ? error.message : "Không chạy lại được agent");
    } finally {
      setBusy(false);
    }
  }

  const agentTone = agentRun?.status === "COMPLETED" ? "ok" : agentRun?.status === "FAILED" ? "crit" : "warn";

  return (
    <section className="view">
      <GuardBanner title="HITL bắt buộc — bác sĩ là người duyệt cuối cùng">
        <li>
          Chỉ bác sĩ nhập và duyệt đơn. AI <b>không kê đơn, không đổi liều, không khuyên ngưng thuốc</b>.
        </li>
        <li>
          Đơn ở trạng thái <b>DRAFT</b> không sinh lịch nhắc. Chỉ khi <b>APPROVED</b> Planning Agent mới chạy.
        </li>
        <li>
          Tên thuốc hiển thị do server tự chốt từ danh mục (<b>display_name</b>) — client không tự đặt được.
        </li>
      </GuardBanner>

      <div className="rx-grid">
        <div className="card">
          <div className="card-head">
            <h2>Nhập đơn thuốc điện tử</h2>
            <div className="spacer" />
            <span className={`pill ${prescription ? "ok" : ""}`}>
              <span className="dot" />
              {prescription ? `${prescription.status} · ${prescription.id.slice(0, 8)}` : "Nháp · chờ duyệt"}
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
                          <option key={route} value={route}>
                            {route}
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
                        placeholder="để trống nếu không ràng buộc"
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
                <b>Backend chặn duyệt — {errorDetails.length} lỗi cần sửa</b>
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
              <h2>Lịch nhắc do Planning Agent sinh</h2>
              <div className="spacer" />
              <span className={`pill mono ${agentRun ? agentTone : ""}`}>
                AGENT · {agentRun?.status ?? "chưa chạy"}
              </span>
            </div>

            <div className="card-body">
              {!agentRun && (
                <p className="empty">
                  Duyệt đơn để Planning Agent tính khung giờ nhắc.
                  <br />
                  Không có đơn APPROVED thì không có lịch — đúng theo guardrail.
                </p>
              )}

              {agentRun && (
                <>
                  <div className="agent-run">
                    <span>{agentRun.agent_type} ·</span>
                    <span className="num">{agentRun.id.slice(0, 8)}</span>
                    <span>· RUNNING →</span>
                    <b style={{ color: `var(--${agentTone})` }}>{agentRun.status}</b>
                    {agentRun.latency_ms !== null && (
                      <>
                        <span>·</span>
                        <span className="num">{agentRun.latency_ms} ms</span>
                      </>
                    )}
                  </div>

                  {agentRun.error_code && (
                    <div className="review-box">
                      <b>
                        {agentRun.status === "NEEDS_REVIEW" ? "Cần bác sĩ xem lại" : "Agent dừng lại"} —{" "}
                        <span className="mono">{agentRun.error_code}</span>
                      </b>
                      {agentRun.error_message && <p className="agent-error-message">{agentRun.error_message}</p>}
                      <p>{errorHint(agentRun.error_code)}</p>
                      <p>Lịch cũ giữ nguyên — agent không tự đoán giờ thay bác sĩ.</p>
                      <div className="row-actions">
                        <button className="btn sm" onClick={retryScheduling} disabled={busy || !prescription}>
                          {busy ? "Đang chạy…" : "↻ Chạy lại Planning Agent"}
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
                              <span>{dose.status}</span>
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}

                  {schedule && schedule.doses.length === 0 && (
                    <p className="empty">Chưa có cữ nào trong hôm nay — lịch có thể bắt đầu từ ngày sau.</p>
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
              <h2>Đơn đã duyệt (JSON)</h2>
              <div className="spacer" />
              <span className="pill mono">POST /prescriptions/{"{id}"}/approve</span>
            </div>
            <div className="card-body">
              <pre>{prescription ? JSON.stringify(prescription, null, 2) : "// Chưa có đơn được duyệt."}</pre>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
