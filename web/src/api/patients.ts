// Slice 2: Patient profile
import { request } from "./client";
import type { DoctorDetail, PatientDetail } from "../types";

export const patientsApi = {
  /**
   * Hồ sơ của chính bác sĩ đang đăng nhập.
   *
   * Cần endpoint riêng vì UserResponse trong token/login chỉ có id/phone/role/
   * status — tên bác sĩ nằm ở bảng doctor_profiles.
   */
  myDoctorProfile: () => request<DoctorDetail>("/doctors/me"),

  /**
   * Tra hồ sơ bệnh nhân theo số điện thoại (Doctor only).
   *
   * Ném ApiError status 404 khi chưa có hồ sơ — đó là kết quả hợp lệ ở form kê
   * đơn (bác sĩ tự điền tay), không phải sự cố, nên nơi gọi phải bắt riêng 404.
   *
   * Số bắt đầu bằng "+84" được buildUrl encode thành %2B qua URLSearchParams —
   * gửi "+" thô thì server đọc thành dấu cách và trả 422.
   */
  patientByPhone: (phone: string) =>
    request<PatientDetail>("/doctors/patients/by-phone", { query: { phone } }),

  patient: (patientId: string) => request<PatientDetail>(`/doctors/patients/${patientId}`),
};
