// Mirror của src/models/clinical.py — đổi model backend thì sửa cả file này.

export type PatientStatus = "RED_ALERT" | "SOS" | "WATCH" | "STABLE";
export type DoseStatus = "PENDING" | "SENT" | "TAKEN" | "LATE" | "SKIPPED" | "MISSED" | "CANCELLED";
export type PrescriptionStatus = "DRAFT" | "APPROVED" | "SUPERSEDED" | "ENDED" | "CANCELLED";
export type ScheduleStatus = "GENERATING" | "ACTIVE" | "SUPERSEDED" | "FAILED" | "NEEDS_REVIEW";
export type AlertState = "OPEN" | "ACKNOWLEDGED" | "ESCALATING" | "RESOLVED" | "CLOSED_FALSE_POSITIVE";
export type AlertKind = "MISSED_STREAK" | "SOS" | "SEVERE_SYMPTOM";
export type Timing = "BEFORE_BREAKFAST" | "AFTER_BREAKFAST" | "AFTER_LUNCH" | "AFTER_DINNER" | "BEDTIME";

export interface PatientRoutine {
  wake: string;
  breakfast: string;
  lunch: string;
  dinner: string;
  sleep: string;
}

export interface Patient {
  id: string;
  name: string;
  initials: string;
  age: number;
  diagnosis: string;
  routine: PatientRoutine;
  adherence_7d: number[];
  adherence_rate: number;
  status: PatientStatus;
  symptom: string;
  consecutive_miss: number;
  last_event: { text: string; tone: string; at: string };
}

export interface AdherenceLog {
  at: string;
  status: DoseStatus | null;
  message: string;
}

export interface WeekCell {
  row: string;
  day: number;
  status: DoseStatus;
}

export interface PatientDetail {
  patient: Patient;
  routine: PatientRoutine;
  logs: AdherenceLog[];
  week: WeekCell[];
}

export interface PrescriptionItemIn {
  drug_name: string;
  dose_per_intake: string;
  frequency_per_day: number;
  timing: Timing;
  treatment_days: number;
  patient_note: string;
}

export interface PrescriptionItem extends PrescriptionItemIn {
  seq: number;
}

export interface Prescription {
  id: string;
  patient_id: string;
  doctor_id: string;
  status: PrescriptionStatus;
  version: number;
  created_at: string;
  approved_at: string | null;
  items: PrescriptionItem[];
}

export interface ValidationIssue {
  code: string;
  field: string;
  message: string;
  item_seq: number | null;
}

export interface ScheduledDose {
  drug_name: string;
  dose_per_intake: string;
  treatment_days: number;
  patient_note: string;
}

export interface ScheduleSlot {
  time: string;
  doses: ScheduledDose[];
}

export interface AgentRun {
  id: string;
  graph: string;
  status: ScheduleStatus;
  latency_ms: number;
  scope: string[];
  denied_ops: string[];
}

export interface MedicationSchedule {
  id: string;
  patient_id: string;
  prescription_id: string;
  status: ScheduleStatus;
  version: number;
  slots: ScheduleSlot[];
  review_notes: string[];
  agent_run: AgentRun;
}

export interface Alert {
  id: string;
  kind: AlertKind;
  patient_id: string;
  title: string;
  detail: string;
  opened_at: string;
  state: AlertState;
  channels: { name: string; status: string }[];
  dispatch_ms: number;
}

export interface DashboardSummary {
  patients_total: number;
  adherence_avg: number;
  response_minutes: number;
  open_alerts: number;
  doses_missed_today: number;
  doses_due_today: number;
  red_alert_precision: number;
}

export interface DrugCatalogEntry {
  drug_id: string;
  brand_name: string;
}
