import type {
  AdherenceReviewSeverity,
  AlertSeverity,
  AlertStatus,
  AlertTriggeredBy,
  PrescriptionStatus,
  RemedyClass,
} from "../types";

type Tone = "crit" | "warn" | "ok";

/** prescriptions.status — khớp (DRAFT | APPROVED | CANCELLED). */
export const PRESCRIPTION_STATUS: Record<PrescriptionStatus, { label: string; tone: Tone }> = {
  DRAFT: { label: "Nháp · Chờ duyệt", tone: "warn" },
  APPROVED: { label: "Đã duyệt", tone: "ok" },
  CANCELLED: { label: "Đã hủy", tone: "crit" },
};

export function prescriptionStatusView(
  status: PrescriptionStatus | string | null | undefined,
): { label: string; tone: Tone | "" } {
  if (!status) return { label: "Nháp · Chờ duyệt", tone: "" };
  return PRESCRIPTION_STATUS[status as PrescriptionStatus] ?? { label: status, tone: "warn" };
}

/** alerts.status — khớp ck_alerts_status (OPEN | ACKNOWLEDGED | RESOLVED). */
export const ALERT_STATUS: Record<AlertStatus, { label: string; tone: Tone }> = {
  OPEN: { label: "Đang mở", tone: "crit" },
  ACKNOWLEDGED: { label: "Đã tiếp nhận", tone: "warn" },
  RESOLVED: { label: "Đã xử lý", tone: "ok" },
};

/** agent_runs.status — khớp ck_agent_runs_status (RUNNING | COMPLETED | FAILED | NEEDS_REVIEW). */
export const AGENT_RUN_STATUS: Record<string, { label: string; tone: Tone }> = {
  COMPLETED: { label: "Hoàn thành", tone: "ok" },
  RUNNING: { label: "Đang xử lý", tone: "warn" },
  FAILED: { label: "Thất bại", tone: "crit" },
  NEEDS_REVIEW: { label: "Cần xem lại", tone: "warn" },
};

export function agentRunStatusView(status: string | null | undefined): { label: string; tone: Tone | "" } {
  if (!status) return { label: "Chưa chạy", tone: "" };
  return AGENT_RUN_STATUS[status] ?? { label: status, tone: "warn" };
}

/** scheduled_doses.status (SCHEDULED | PENDING | TAKEN | SKIPPED | MISSED | SNOOZED). */
export const DOSE_STATUS: Record<string, string> = {
  SCHEDULED: "Chưa đến giờ",
  PENDING: "Đang chờ",
  TAKEN: "Đã uống",
  SKIPPED: "Đã bỏ qua",
  MISSED: "Đã bỏ lỡ",
  SNOOZED: "Đã hoãn",
};

export function doseStatusLabel(status: string | null | undefined): string {
  if (!status) return "";
  return DOSE_STATUS[status.toUpperCase()] ?? status;
}

/** health_surveys.status (SUBMITTED | COMPLETED | PENDING | DRAFT). */
export const SURVEY_STATUS: Record<string, { label: string; tone: Tone }> = {
  SUBMITTED: { label: "Đã nộp", tone: "ok" },
  COMPLETED: { label: "Hoàn thành", tone: "ok" },
  PENDING: { label: "Đang chờ", tone: "warn" },
  DRAFT: { label: "Bản nháp", tone: "warn" },
};

export function surveyStatusView(status: string | null | undefined): { label: string; tone: Tone | "" } {
  if (!status) return { label: "", tone: "" };
  return SURVEY_STATUS[status.toUpperCase()] ?? { label: status, tone: "ok" };
}

export function surveyStatusLabel(status: string | null | undefined): string {
  return surveyStatusView(status).label;
}

/** alerts.severity — khớp ck_alerts_severity. */
export const ALERT_SEVERITY: Record<AlertSeverity, { label: string; tone: Tone }> = {
  CRITICAL: { label: "Nguy kịch", tone: "crit" },
  HIGH: { label: "Cao", tone: "crit" },
  MEDIUM: { label: "Trung bình", tone: "warn" },
};

/** alerts.triggered_by_type — khớp ck_alerts_triggered_by_type. */
export const ALERT_TRIGGER: Record<AlertTriggeredBy, string> = {
  SOS_BUTTON: "Bệnh nhân bấm SOS",
  SEVERE_SYMPTOM: "Triệu chứng nặng",
  MISSED_DOSES: "Chuỗi bỏ liều",
  ADHERENCE_REVIEW: "Đánh giá tuân thủ hàng đêm",
  ADVERSE_EVENT: "Triệu chứng nghi ngờ từ chat",
};

/** alerts.alert_type — khớp ck_alerts_alert_type (RED_ALERT | WARNING | SUSPECTED_ADVERSE_EVENT). */
export const ALERT_TYPE: Record<string, string> = {
  RED_ALERT: "Cảnh báo khẩn",
  WARNING: "Cảnh báo nhắc nhở",
  SUSPECTED_ADVERSE_EVENT: "Nghi ngờ tác dụng phụ",
};

export function alertTypeLabel(type: string): string {
  return ALERT_TYPE[type] ?? type;
}

export const SYMPTOM_LABELS: Record<string, string> = {
  FATIGUE: "Mệt mỏi",
  DIZZINESS: "Chóng mặt",
  NAUSEA: "Buồn nôn",
  HEADACHE: "Đau đầu",
  VOMITING: "Nôn mửa",
  FEVER: "Sốt",
  INSOMNIA: "Mất ngủ",
  RASH: "Phát ban",
  CHEST_PAIN: "Đau ngực",
  SHORTNESS_OF_BREATH: "Khó thở",
  STOMACH_ACHE: "Đau dạ dày / Đau bụng",
  DIARRHEA: "Tiêu chảy",
  ALLERGY: "Dị ứng",
  NONE: "Không có",
  OTHER: "Khác",
};

export function symptomLabel(code: string): string {
  if (!code) return "";
  const upper = code.trim().toUpperCase();
  return SYMPTOM_LABELS[upper] ?? code;
}

export function formatAlertMessage(message: string | null | undefined): string {
  if (!message || !message.trim()) return "Không có mô tả kèm theo.";

  // Pattern: "Severe symptom(s) reported: FATIGUE, NAUSEA"
  const severeMatch = message.match(/Severe symptom\(?s?\)?\s*(?:reported|detected):\s*(.+)/i);
  if (severeMatch) {
    const rawCodes = severeMatch[1].split(",").map((s) => s.trim()).filter(Boolean);
    const translated = rawCodes.map((code) => symptomLabel(code)).join(", ");
    return `Ghi nhận triệu chứng nặng: ${translated}`;
  }

  // Pattern: "Emergency SOS button triggered by patient"
  if (/emergency sos/i.test(message)) {
    return "Bệnh nhân đã bấm nút khẩn cấp SOS";
  }

  return message;
}

export const REVIEW_SEVERITY: Record<AdherenceReviewSeverity, { label: string; tone: Tone }> = {
  MILD: { label: "Nhẹ", tone: "warn" },
  MODERATE: { label: "Trung bình", tone: "warn" },
  SEVERE: { label: "Nghiêm trọng", tone: "crit" },
};

export const REMEDY_CLASS: Record<RemedyClass, string> = {
  RESCHEDULE_TIMING: "Lệch múi giờ sinh hoạt",
  SUSPECTED_SIDE_EFFECT: "Nghi tác dụng phụ",
  DELIBERATE_REFUSAL: "Chủ động từ chối",
  DISENGAGEMENT: "Mất kết nối điều trị",
  EXTERNAL_DISRUPTION: "Gián đoạn ngoại cảnh",
  UNCLEAR: "Chưa rõ nguyên nhân",
};

export function alertStatusView(status: string): { label: string; tone: Tone } {
  return ALERT_STATUS[status as AlertStatus] ?? { label: status, tone: "warn" };
}

export function alertSeverityView(severity: string): { label: string; tone: Tone } {
  return ALERT_SEVERITY[severity as AlertSeverity] ?? { label: severity, tone: "warn" };
}

export function alertTriggerLabel(trigger: string): string {
  return ALERT_TRIGGER[trigger as AlertTriggeredBy] ?? trigger;
}

export function reviewSeverityView(severity: string): { label: string; tone: Tone } {
  return REVIEW_SEVERITY[severity as AdherenceReviewSeverity] ?? { label: severity, tone: "warn" };
}

export function remedyClassLabel(remedyClass: string | null): string {
  if (!remedyClass) return "Chưa phân loại";
  return REMEDY_CLASS[remedyClass as RemedyClass] ?? remedyClass;
}

/** Ngưỡng màu cho tỷ lệ tuân thủ — KPI MVP là 70%. */
export function adherenceTone(value: number): Tone {
  if (value >= 85) return "ok";
  if (value >= 70) return "warn";
  return "crit";
}

/** Xếp mức ưu tiên một dòng bệnh nhân từ số cảnh báo mở + tỷ lệ tuân thủ. */
export function patientPriority(
  openAlerts: number,
  adherenceRate: number,
): { label: string; tone: Tone; row: string } {
  if (openAlerts > 0) return { label: "Cần xử lý", tone: "crit", row: "sev-red" };
  if (adherenceRate < 70) return { label: "Theo dõi", tone: "warn", row: "sev-watch" };
  return { label: "Ổn định", tone: "ok", row: "sev-ok" };
}

/**
 * Bệnh nhân được tạo tự động lúc bác sĩ kê đơn (find-or-create theo số điện
 * thoại) có patient_profiles.name là chuỗi literal "NULL" — placeholder cố ý
 * của backend, bệnh nhân tự sửa khi onboarding (POST /patients/me/profile).
 * Đừng hiển thị nguyên chuỗi đó cho bác sĩ.
 */
export function patientDisplayName(name: string | null | undefined): string {
  const trimmed = (name ?? "").trim();
  if (!trimmed || trimmed === "NULL") return "Chưa có hồ sơ";
  return trimmed;
}

/** Hai chữ cái đầu để dựng avatar — backend không trả sẵn initials. */
export function initialsOf(name: string): string {
  const trimmedName = patientDisplayName(name);
  if (trimmedName === "Chưa có hồ sơ") return "–";
  const parts = trimmedName.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[parts.length - 2][0] + parts[parts.length - 1][0]).toUpperCase();
}

/** ISO datetime -> "HH:MM DD/MM" theo giờ máy bác sĩ. */
export function formatDateTime(value: string | null): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("vi-VN", {
    hour: "2-digit",
    minute: "2-digit",
    day: "2-digit",
    month: "2-digit",
  });
}

/** ISO datetime -> "HH:MM" giờ địa phương. Cắt chuỗi ISO sẽ ra giờ UTC. */
export function formatTime(value: string | null): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" });
}

/** dose_value là NUMERIC(10,3) — DB trả về "1.000" cho liều 1 viên; bỏ số 0 thừa. */
export function formatDoseValue(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === "") return "";
  const num = Number(value);
  return Number.isFinite(num) ? String(num) : String(value);
}

export function formatDate(value: string | null): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleDateString("vi-VN", { day: "2-digit", month: "2-digit", year: "numeric" });
}

/** YYYY-MM-DD theo giờ địa phương (toISOString sẽ lệch ngày do đổi sang UTC). */
export function isoDate(date: Date): string {
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${date.getFullYear()}-${month}-${day}`;
}

/**
 * Dải số trang cho pagination dạng pill-strip: luôn có trang đầu/cuối,
 * current±1, còn lại gộp thành "ellipsis". Ví dụ current=5,total=10 ->
 * [1, "ellipsis", 4, 5, 6, "ellipsis", 10].
 */
export function paginationRange(current: number, total: number): (number | "ellipsis")[] {
  if (total <= 1) return [1];

  const pages = new Set<number>([1, total, current]);
  if (current - 1 >= 1) pages.add(current - 1);
  if (current + 1 <= total) pages.add(current + 1);

  const sorted = [...pages].sort((a, b) => a - b);
  const result: (number | "ellipsis")[] = [];
  sorted.forEach((page, index) => {
    if (index > 0 && page - sorted[index - 1] > 1) result.push("ellipsis");
    result.push(page);
  });
  return result;
}
