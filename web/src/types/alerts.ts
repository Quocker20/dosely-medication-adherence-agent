// Part of src/types/ — xem index.ts cho ràng buộc sync với backend.
// Slice 7 — Adherence & Alerts

export type AlertStatus = "OPEN" | "ACKNOWLEDGED" | "RESOLVED";
export type AlertSeverity = "CRITICAL" | "HIGH" | "MEDIUM";
export type AlertTriggeredBy = "SOS_BUTTON" | "SEVERE_SYMPTOM" | "MISSED_DOSES" | "ADHERENCE_REVIEW";

export interface AlertDetail {
  id: string;
  patient_id: string;
  assigned_doctor_id: string | null;
  triggered_by_type: string;
  alert_type: string;
  severity: string;
  status: string;
  message: string | null;
  created_at: string;
}

export interface AdherenceSummary {
  patient_id: string;
  from_date: string;
  to_date: string;
  adherence_rate: number;
  total_doses: number;
  taken_doses: number;
  skipped_doses: number;
  missed_doses: number;
}
