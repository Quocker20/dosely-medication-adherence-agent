// Part of src/types/ — xem index.ts cho ràng buộc sync với backend.
// Slice 8 — Dashboard (Doctor Portal)

import type { AlertDetail } from "./alerts";

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

export interface RoutineUpdatedRealtimeEvent extends WebSocketEventStream {
  event_type: "routine.updated";
  data: {
    patient_id: string;
    updated_at: string;
  };
}

export interface ScheduleUpdatedRealtimeEvent extends WebSocketEventStream {
  event_type: "schedule.updated";
  data: {
    patient_id: string;
    updated_at: string;
  };
}

export type PatientRealtimeEvent = RoutineUpdatedRealtimeEvent | ScheduleUpdatedRealtimeEvent;
