// Slice 4: Patient routine
import { request } from "./client";
import type { PatientRoutine, UpdatePatientRoutineRequest } from "../types";

export const routineApi = {
  patientRoutine: (patientId: string) => request<PatientRoutine>(`/patients/${patientId}/routine`),
  updatePatientRoutine: (patientId: string, payload: UpdatePatientRoutineRequest) =>
    request<PatientRoutine>(`/patients/${patientId}/routine`, { method: "PUT", body: payload }),
};
