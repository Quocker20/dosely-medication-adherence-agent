// Part of src/types/ — Caregiver module
export interface CaregiverLinkDetail {
  id: string;
  patient_id: string;
  phone: string;
  relationship: string | null;
  link_code: string | null;
  telegram_deep_link: string | null;
  status: "PENDING" | "ACTIVE" | "BLOCKED" | "INACTIVE" | string;
  telegram_bound_at: string | null;
  last_message_sent_at: string | null;
  created_at: string;
}

export interface CreateCaregiverLinkRequest {
  caregiver_phone: string;
  relationship?: string | null;
}
