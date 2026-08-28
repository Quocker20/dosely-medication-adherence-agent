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
