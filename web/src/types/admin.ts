// Part of src/types/ — xem index.ts cho ràng buộc sync với backend.
// Admin — Doctor management & audit logs

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
