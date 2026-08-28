// Part of src/types/ — xem index.ts cho ràng buộc sync với backend.
// Slice 4 — Patient routine (đầu vào của Planning Agent)

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

/** PUT /patients/{id}/routine — mọi trường optional, "HH:MM:SS" hoặc "HH:MM". */
export interface UpdateRoutineRequest {
  wake_time?: string;
  breakfast_time?: string;
  lunch_time?: string;
  dinner_time?: string;
  sleep_time?: string;
}
