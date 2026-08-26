// Part of src/types/ — xem index.ts cho ràng buộc sync với backend.
// Slice 5 — Prescriptions

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
 *
 * name/dob/sex là BẮT BUỘC ở backend (CreatePrescriptionRequest trong
 * src/modules/prescriptions/schemas.py) — kể cả khi bệnh nhân đã tồn tại, để
 * hồ sơ luôn đủ dữ liệu nhân khẩu. dob dạng YYYY-MM-DD, phải sau 1900-01-01 và
 * không được ở tương lai.
 */
export interface CreatePrescriptionRequest {
  phone: string;
  name: string;
  dob: string;
  sex: "MALE" | "FEMALE" | "OTHER";
  emergency_note: string | null;
  diagnosis_note: string | null;
  items: PrescriptionItemIn[];
}

/** temp_password chỉ khác null khi call này vừa tạo mới tài khoản bệnh nhân. */
export interface CreatePrescriptionResponse {
  prescription: PrescriptionDetail;
  temp_password: string | null;
}
