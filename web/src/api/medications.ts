// Slice 3: Medications
import { request } from "./client";
import type { MedicationDetail, PageResponse } from "../types";

export const medicationsApi = {
  medications: (params: { page?: number; size?: number; search?: string } = {}) =>
    request<PageResponse<MedicationDetail>>("/medications", {
      query: {
        page: params.page ?? 1,
        size: params.size ?? 100,
        search: params.search && params.search.trim().length >= 2 ? params.search.trim() : undefined,
      },
    }),

  medication: (medicationId: string) => request<MedicationDetail>(`/medications/${medicationId}`),
};
