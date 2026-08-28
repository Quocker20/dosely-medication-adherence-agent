// Part of src/types/ — xem index.ts cho ràng buộc sync với backend.
// Slice 2 — Patient profile (src/modules/patients/schemas.py)

import type { PatientRoutine, UpdateRoutineRequest } from "./routine";

/**
 * Trả về bởi GET /patients/by-phone (Doctor only).
 *
 * dob/sex/emergency_note là Optional ở backend: bệnh nhân được tạo tự động lúc
 * bác sĩ kê đơn (find-or-create theo số điện thoại) chỉ có phone, các trường
 * nhân khẩu để trống tới khi ai đó điền. Form kê đơn vì thế chỉ khoá những ô
 * thực sự có dữ liệu, không khoá ô rỗng.
 */
export interface PatientDetail {
  user_id: string;
  phone: string;
  role: string;
  status: string;
  name: string;
  dob: string | null;
  sex: string | null;
  timezone: string;
  privacy_consent_status: string | null;
  emergency_note: string | null;
  created_at: string;
  updated_at: string;
}

/** POST /patients/me/profile — hoàn tất onboarding, xoá cờ need_onboarding. */
export interface PatientOnboardingRequest {
  name: string;
  dob?: string;
  sex?: string;
  timezone?: string;
  emergency_note?: string;
  routine: UpdateRoutineRequest;
}

export interface PatientProfileDetailResponse {
  profile: PatientDetail;
  routine: PatientRoutine;
}
