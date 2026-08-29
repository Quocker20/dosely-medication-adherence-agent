export interface AdherenceLog {
  id: string;
  scheduled_dose_id: string | null;
  patient_id: string;
  action: string;
  performed_at: string;
  action_source: string;
  payload: Record<string, unknown>;
  idempotency_key: string | null;
}

export type AdherenceReviewSeverity = "MILD" | "MODERATE" | "SEVERE";
export type AdherenceReviewAction = "NONE" | "PATIENT_NOTIFICATION" | "DOCTOR_WARNING" | "DOCTOR_ALERT";
export type RemedyClass =
  | "RESCHEDULE_TIMING"
  | "SUSPECTED_SIDE_EFFECT"
  | "DELIBERATE_REFUSAL"
  | "DISENGAGEMENT"
  | "EXTERNAL_DISRUPTION"
  | "UNCLEAR";

export interface AdherenceReviewDetail {
  id: string;
  patient_id: string;
  review_date: string;
  window_start: string;
  window_end: string;
  severity: AdherenceReviewSeverity;
  days_in_severity: number;
  remedy_class: RemedyClass | null;
  action_taken: AdherenceReviewAction;
  indicators: Record<string, unknown>;
  llm_reasoning: string | null;
  llm_confidence: string | null;
  created_at: string;
}

