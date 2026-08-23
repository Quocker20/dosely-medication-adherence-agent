// Helper riêng của patient portal. Cố tình không dùng src/utils/labels.ts:
// bên đó format theo góc nhìn bác sĩ (ngày/giờ VN đầy đủ), còn ở đây là góc
// nhìn bệnh nhân (giờ ngắn gọn, nhãn trạng thái cữ thuốc).
import type { ScheduledDoseRow } from "../../../types";

export type DoseAction = (dose: ScheduledDoseRow, type: "TAKEN" | "SNOOZE" | "SKIPPED") => Promise<void>;

export const isoDate = (date: Date) => date.toLocaleDateString("en-CA", { timeZone: "Asia/Ho_Chi_Minh" });

export function prettyTime(value: string) {
  const parsed = new Date(value);
  return Number.isNaN(parsed.valueOf()) ? value.slice(0, 5) : parsed.toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" });
}

export function doseStatus(status: string) {
  const value = status.toUpperCase();
  if (value === "TAKEN") return ["Đã uống", "taken"] as const;
  if (value === "SKIPPED" || value === "MISSED") return [value === "SKIPPED" ? "Đã bỏ qua" : "Đã lỡ", "missed"] as const;
  if (value === "SNOOZED") return ["Đã hoãn", "late"] as const;
  return ["Sắp tới", "upcoming"] as const;
}

export function isDoseLocked(dose: ScheduledDoseRow) {
  return dose.status.toUpperCase() === "PENDING" && new Date(dose.current_scheduled_at).getTime() > Date.now();
}
