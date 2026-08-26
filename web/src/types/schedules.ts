// Part of src/types/ — xem index.ts cho ràng buộc sync với backend.
// Slice 6 — Schedules & Agents

/** 202 Accepted: agent chạy nền, poll GET /agent-runs/{id} để biết kết quả. */
export interface AgentRunAsyncResponse {
  agent_run_id: string;
  status: string;
  message: string;
}

export interface AgentRunStatus {
  id: string;
  agent_type: string;
  patient_id: string;
  prescription_id: string | null;
  trigger_type: string;
  graph_version: string;
  status: string;
  latency_ms: number | null;
  error_code: string | null;
  /** Lý do dừng dạng đọc được — error_code chỉ là tên class exception. */
  error_message: string | null;
  generated_dose_count: number | null;
  created_at: string;
}

/** Backend trả doses dạng List[Dict] (schema.md §6.4), không phải model typed. */
export interface ScheduledDoseRow {
  scheduled_dose_id: string;
  medication_name: string;
  current_scheduled_at: string;
  status: string;
  snooze_count: number;
  prescription_item_id?: string | null;
  medication_id?: string | null;
  dose_slot?: string | null;
  dose_value?: string | number | null;
  dose_unit?: string | null;
  meal_relation?: string | null;
}

export interface ActiveSchedule {
  patient_id: string;
  date: string;
  doses: ScheduledDoseRow[];
}

export interface VoiceChatResponse {
  transcript: string;
  response: string;
  audio_base64: string | null;
}
