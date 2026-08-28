import { useState } from "react";

import { ApiError, api } from "../../../api";
import Icon from "./Icon";

const routineFields: Array<{ key: "wake_time" | "breakfast_time" | "lunch_time" | "dinner_time" | "sleep_time"; label: string; fallback: string }> = [
  { key: "wake_time", label: "Thức dậy", fallback: "06:30" },
  { key: "breakfast_time", label: "Ăn sáng", fallback: "07:00" },
  { key: "lunch_time", label: "Ăn trưa", fallback: "11:30" },
  { key: "dinner_time", label: "Ăn tối", fallback: "18:00" },
  { key: "sleep_time", label: "Đi ngủ", fallback: "22:00" },
];

/**
 * Onboarding lần đầu cho bệnh nhân — chỉ thu thập giờ sinh hoạt (khớp
 * src/modules/patients/service.py update_routine: "mobile onboarding flow
 * intentionally collects routine data only"). Hồ sơ (tên, ngày sinh...) là dữ
 * liệu do đội ngũ y tế nhập, không phải việc của patient tự chỉnh ở đây.
 *
 * Gate ở PatientPortal theo session.needOnboarding (POST /auth/login|refresh),
 * không suy ra từ nội dung routine đã có — đó chính là bug đã sửa ở backend:
 * bác sĩ seed routine đầy đủ thì suy luận theo routine luôn sai.
 */
export default function OnboardingView({ patientId, onDone }: { patientId: string; onDone: () => void }) {
  const [times, setTimes] = useState<Record<string, string>>(
    Object.fromEntries(routineFields.map((field) => [field.key, field.fallback])),
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      await api.updateRoutine(patientId, times);
      onDone();
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "Không lưu được thói quen, vui lòng thử lại");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="web-card patient-form">
      <div className="form-hero">
        <span><Icon name="clock" size={25} /></span>
        <div>
          <h1>Thiết lập thói quen sinh hoạt</h1>
          <p>Chọn giờ sinh hoạt hằng ngày để lên lịch uống thuốc chính xác.</p>
        </div>
      </div>

      <div className="form-section">
        <span className="form-step">01</span>
        <h2>Giờ sinh hoạt hằng ngày</h2>
        {routineFields.map((field) => (
          <div key={field.key} style={{ marginBottom: 12 }}>
            <h3>{field.label}</h3>
            <input
              className="survey-other-input"
              type="time"
              value={times[field.key]}
              onChange={(event) => setTimes((prev) => ({ ...prev, [field.key]: event.target.value }))}
            />
          </div>
        ))}
      </div>

      {error && (
        <div className="patient-error">
          <span>{error}</span>
        </div>
      )}

      <div className="form-submit-row">
        <p><Icon name="shield" size={16} /> Dữ liệu được bảo mật</p>
        <button className="survey-submit" disabled={busy} onClick={() => void submit()}>
          {busy ? "Đang lưu…" : "Lưu & bắt đầu sử dụng"}
        </button>
      </div>
    </section>
  );
}
