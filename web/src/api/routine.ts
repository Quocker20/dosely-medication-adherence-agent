// Slice 4: Patient routine
import { request } from "./client";
import type { PatientRoutine } from "../types";

export const routineApi = {
  patientRoutine: (patientId: string) => request<PatientRoutine>(`/patients/${patientId}/routine`),
};
