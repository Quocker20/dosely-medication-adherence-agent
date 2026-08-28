// Slice 4: Patient routine
import { request } from "./client";
import type { PatientRoutine, UpdateRoutineRequest } from "../types";

export const routineApi = {
  patientRoutine: (patientId: string) => request<PatientRoutine>(`/patients/${patientId}/routine`),

  /** PUT /patients/{id}/routine — cách bệnh nhân hoàn tất onboarding (chỉ routine, không đổi profile). */
  updateRoutine: (patientId: string, body: UpdateRoutineRequest) =>
    request<PatientRoutine>(`/patients/${patientId}/routine`, { method: "PUT", body }),
};
