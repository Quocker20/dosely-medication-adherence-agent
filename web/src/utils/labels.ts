import type { AlertSeverity, AlertStatus, AlertTriggeredBy } from "../types";

type Tone = "crit" | "warn" | "ok";

/** alerts.status — khớp ck_alerts_status (OPEN | ACKNOWLEDGED | RESOLVED). */
export const ALERT_STATUS: Record<AlertStatus, { label: string; tone: Tone }> = {
  OPEN: { label: "Đang mở", tone: "crit" },
  ACKNOWLEDGED: { label: "Đã tiếp nhận", tone: "warn" },
  RESOLVED: { label: "Đã xử lý", tone: "ok" },
};

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
