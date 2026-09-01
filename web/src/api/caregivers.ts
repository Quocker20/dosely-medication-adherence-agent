import { request } from "./client";
import type { CaregiverLinkDetail, CreateCaregiverLinkRequest } from "../types";

export const caregiversApi = {
  getCaregivers: (patientId: string) =>
    request<CaregiverLinkDetail[]>(`/patients/${patientId}/caregivers`),

  createCaregiver: (patientId: string, body: CreateCaregiverLinkRequest) =>
    request<CaregiverLinkDetail>(`/patients/${patientId}/caregivers`, {
      method: "POST",
      body,
    }),

  deleteCaregiver: (patientId: string, caregiverLinkId: string) =>
    request<{ message: string }>(`/patients/${patientId}/caregivers/${caregiverLinkId}`, {
      method: "DELETE",
    }),
};
