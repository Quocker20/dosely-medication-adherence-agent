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
 * Onboarding lần đầu cho bệnh nhân — gate ở PatientPortal theo session.needOnboarding
 * (POST /auth/login|refresh), không suy ra từ nội dung routine đã có (đó chính là
 * bug đã sửa ở backend: bác sĩ seed routine đầy đủ thì suy luận theo routine luôn sai).
 */
export default function OnboardingView({ onDone }: { onDone: () => void }) {
  const [name, setName] = useState("");
  const [times, setTimes] = useState<Record<string, string>>(
    Object.fromEntries(routineFields.map((field) => [field.key, field.fallback])),
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit() {
    if (name.trim().length === 0) {
      setError("Vui lòng nhập họ tên");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await api.onboardProfile({ name: name.trim(), routine: times });
      onDone();
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "Không lưu được thông tin, vui lòng thử lại");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="web-card patient-form">
      <div className="form-hero">
        <span><Icon name="clock" size={25} /></span>
        <div>
          <h1>Hoàn tất hồ sơ của bạn</h1>
          <p>Cho chúng tôi biết tên và giờ sinh hoạt để lên lịch uống thuốc chính xác.</p>
        </div>
      </div>

      <div className="form-section">
        <span className="form-step">01</span>
        <h2>Họ và tên</h2>
        <input
          className="survey-other-input"
          placeholder="Nguyễn Văn A"
          value={name}
          onChange={(event) => setName(event.target.value)}
          maxLength={255}
        />
      </div>

      <div className="form-section">
        <span className="form-step">02</span>
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
          {busy ? "Đang lưu…" : "Bắt đầu sử dụng"}
        </button>
      </div>
    </section>
  );
}
