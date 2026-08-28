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

/** PATCH-like PUT body: omitted fields must remain untouched on the server. */
export interface UpdatePatientRoutineRequest {
  wake_time?: string | null;
  breakfast_time?: string | null;
  lunch_time?: string | null;
  dinner_time?: string | null;
  sleep_time?: string | null;
}
