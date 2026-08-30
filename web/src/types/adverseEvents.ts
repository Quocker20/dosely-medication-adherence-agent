export interface SuspectedAdverseEvent {
  id: string; patient_id: string; patient_name: string; raw_text: string;
  symptoms: Array<{ name: string; severity: string; onset?: string | null; description?: string | null }>;
  related_medications: Array<{ medication_id?: string | null; drug_name: string; taken_at?: string | null; context_type?: "RECENTLY_TAKEN" | "ACTIVE_PRESCRIPTION" }>;
  risk_level: "LOW" | "MODERATE" | "HIGH" | "CRITICAL";
  causality: "UNASSESSED" | "POSSIBLE" | "UNLIKELY" | "CONFIRMED";
  review_status: "NEW" | "ACKNOWLEDGED" | "REVIEWED";
  clinician_note: string | null; reported_at: string;
}
