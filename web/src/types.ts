// Mirror của schema backend hiện tại — đổi model backend thì sửa cả file này.
// Nguồn: src/core/response.py, src/common/schemas.py, src/modules/*/schemas.py
// và bảng endpoint trong docs/api-contract.md.

// ---------------------------------------------------------------------------
// Envelope chung (src/core/response.py:APIResponse)
// ---------------------------------------------------------------------------

/** Mọi endpoint REST đều bọc payload trong envelope này, kể cả khi lỗi. */
export interface ApiEnvelope<T> {
  success: boolean;
  code: number;
  message: string;
  data: T | null;
  errors?: unknown;
}

/** Wrapper phân trang chuẩn (src/common/schemas.py:PageResponse). */
export interface PageResponse<T> {
  content: T[];
  page_no: number;
  page_size: number;
  total_elements: number;
  total_pages: number;
  last: boolean;
}

// ---------------------------------------------------------------------------
// Slice 1 — Authentication
// ---------------------------------------------------------------------------

export type UserRole = "ADMIN" | "DOCTOR" | "PATIENT" | "CAREGIVER";

export interface UserResponse {
  id: string;
  phone: string;
  role: UserRole;
  status: string;
}

export interface AuthTokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
  is_first_login: boolean;
  user: UserResponse;
}

// ---------------------------------------------------------------------------
// Slice 3 — Medications (danh mục dược phẩm)
// ---------------------------------------------------------------------------

export interface MedicationDetail {
  id: string;
  name: string;
  composition: string | null;
  manufacturer: string | null;
  uses: string | null;
  side_effects: string | null;
  image_url: string | null;
  source_name: string;
  is_active: boolean;
}

// ---------------------------------------------------------------------------
// Slice 4 — Patient routine (đầu vào của Planning Agent)
// ---------------------------------------------------------------------------

/** Các *_time là kiểu time của Postgres — trả về dạng "HH:MM:SS", có thể null. */
export interface PatientRoutine {
  id: string;
  patient_id: string;
  wake_time: string | null;
  breakfast_time: string | null;
  lunch_time: string | null;
  dinner_time: string | null;
  sleep_time: string | null;
  updated_at: string;
}

// ---------------------------------------------------------------------------
// Slice 5 — Prescriptions
// ---------------------------------------------------------------------------

export type PrescriptionStatus = "DRAFT" | "APPROVED" | "CANCELLED";

/**
 * Dosing rule của một dòng thuốc. Không có display_name — server tự snapshot
 * từ Medication.name lúc ghi, client gửi lên sẽ bị bỏ qua.
 * Các *_dose là Decimal phía backend nên gửi số hoặc null, đừng gửi chuỗi rỗng.
 */
export interface PrescriptionItemIn {
  medication_id: string;
  dose_unit: string;
  morning_dose: number | null;
  noon_dose: number | null;
  evening_dose: number | null;
  bedtime_dose: number | null;
  route: string;
  meal_relation: string | null;
  minimum_interval_minutes: number | null;
  start_date: string;
  end_date: string | null;
  instructions: string | null;
}

export interface PrescriptionItemDetail {
  id: string;
  prescription_id: string;
  medication_id: string | null;
  display_name: string;
  dose_unit: string;
  morning_dose: string | number | null;
  noon_dose: string | number | null;
  evening_dose: string | number | null;
  bedtime_dose: string | number | null;
  route: string;
  meal_relation: string | null;
  minimum_interval_minutes: number | null;
  start_date: string;
  end_date: string | null;
  instructions: string | null;
  created_at: string;
}

export interface PrescriptionDetail {
  id: string;
  patient_id: string;
  doctor_id: string | null;
  status: string;
  diagnosis_note: string | null;
  approved_at: string | null;
  created_at: string;
  items: PrescriptionItemDetail[];
}

/**
 * POST /prescriptions nhận bệnh nhân qua số điện thoại (find-or-create),
 * không phải patient_id.
 */
export interface CreatePrescriptionRequest {
  phone: string;
  diagnosis_note: string | null;
  items: PrescriptionItemIn[];
}

/** temp_password chỉ khác null khi call này vừa tạo mới tài khoản bệnh nhân. */
export interface CreatePrescriptionResponse {
  prescription: PrescriptionDetail;
  temp_password: string | null;
}

// ---------------------------------------------------------------------------
// Slice 6 — Schedules & Agents
// ---------------------------------------------------------------------------

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

// ---------------------------------------------------------------------------
// Slice 7 — Adherence & Alerts
// ---------------------------------------------------------------------------

export type AlertStatus = "OPEN" | "ACKNOWLEDGED" | "RESOLVED";
export type AlertSeverity = "CRITICAL" | "HIGH" | "MEDIUM";
export type AlertTriggeredBy = "SOS_BUTTON" | "SEVERE_SYMPTOM" | "MISSED_DOSES";

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

// ---------------------------------------------------------------------------
// Slice 8 — Dashboard (Doctor Portal)
// ---------------------------------------------------------------------------

export interface DashboardPatientListItem {
  patient_id: string;
  patient_name: string;
  adherence_rate: number;
  open_alerts_count: number;
  last_survey_date: string | null;
}

/**
 * Cố tình hẹp hơn AdherenceSummary: dashboard hiển thị tỷ lệ trên cửa sổ trượt
 * (window_days) chứ không phải khoảng [from, to] do client chọn.
 */
export interface DashboardAdherenceSummary {
  adherence_rate: number;
  total_doses: number;
  taken_doses: number;
  skipped_doses: number;
  missed_doses: number;
  window_days: number;
}

export interface DashboardPatientSummary {
  user_id: string;
  name: string;
  phone: string;
}

export interface DashboardPatientDetail {
  patient: DashboardPatientSummary;
  active_prescriptions_count: number;
  adherence_summary: DashboardAdherenceSummary;
  recent_alerts: AlertDetail[];
}

/** Frame đẩy qua WS /ws/dashboard — event_type hiện có: alert.opened, alert.updated. */
export interface WebSocketEventStream {
  event_type: string;
  timestamp: string;
  data: Record<string, unknown>;
}

// ---------------------------------------------------------------------------
// Admin — Doctor management & audit logs
// ---------------------------------------------------------------------------

export type DoctorStatus = "ACTIVE" | "INACTIVE";

export interface DoctorDetail {
  user_id: string;
  phone: string;
  role: "DOCTOR";
  status: DoctorStatus | string;
  name: string;
  license_no: string;
  specialty: string | null;
  created_at: string;
}

export interface CreateDoctorRequest {
  phone: string;
  name: string;
  license_no: string;
  specialty: string | null;
}

export interface UpdateDoctorRequest {
  name?: string;
  specialty?: string | null;
  status?: DoctorStatus;
}

export interface CreateDoctorResponse {
  doctor: DoctorDetail;
  temp_password: string;
}

export interface AuditLog {
  id: string;
  actor_user_id: string | null;
  action: string;
  entity_type: string;
  entity_id: string | null;
  old_values: Record<string, unknown> | null;
  new_values: Record<string, unknown> | null;
  ip_address: string | null;
  created_at: string;
}
