import type { AlertKind, DoseStatus, PatientStatus, Timing } from "../types";

export const PATIENT_STATUS: Record<PatientStatus, { label: string; tone: "crit" | "warn" | "ok"; row: string }> = {
  RED_ALERT: { label: "RED ALERT", tone: "crit", row: "sev-red" },
  SOS: { label: "SOS", tone: "crit", row: "sev-red" },
  WATCH: { label: "Theo dõi", tone: "warn", row: "sev-watch" },
  STABLE: { label: "Ổn định", tone: "ok", row: "sev-ok" },
};

export const ALERT_KIND: Record<AlertKind, string> = {
  MISSED_STREAK: "Chuỗi bỏ liều",
  SOS: "SOS",
  SEVERE_SYMPTOM: "Triệu chứng nặng",
};

export const TIMING_LABEL: Record<Timing, string> = {
  BEFORE_BREAKFAST: "Trước ăn sáng",
  AFTER_BREAKFAST: "Sau ăn sáng",
  AFTER_LUNCH: "Sau ăn trưa",
  AFTER_DINNER: "Sau ăn tối",
  BEDTIME: "Trước khi ngủ",
};

export const TIMINGS = Object.keys(TIMING_LABEL) as Timing[];

/** Ô lưới 7 ngày: gom các trạng thái liều về 3 nhóm màu. */
export function doseCell(status: DoseStatus): { cls: string; glyph: string; title: string } {
  if (status === "TAKEN") return { cls: "taken", glyph: "✓", title: "Đã uống" };
  if (status === "LATE") return { cls: "late", glyph: "~", title: "Uống muộn" };
  if (status === "MISSED" || status === "SKIPPED") {
    return { cls: "miss", glyph: "✕", title: "Bỏ qua / không phản hồi" };
  }
  return { cls: "", glyph: "·", title: "Chưa tới giờ" };
}

/** Ngưỡng màu cho tỷ lệ tuân thủ — KPI MVP là 70%. */
export function adherenceTone(value: number): "ok" | "warn" | "crit" {
  if (value >= 85) return "ok";
  if (value >= 70) return "warn";
  return "crit";
}
