import { request } from "./client";
import type { AdherenceLog, AdherenceSummary, PageResponse } from "../types";

export const adherenceApi = {
  adherenceSummary: (patientId: string, from: string, to: string) =>
    request<AdherenceSummary>(`/patients/${patientId}/adherence`, { query: { from, to } }),
  adherenceLogs: (patientId: string, from: string, to: string, size = 20) =>
    request<PageResponse<AdherenceLog>>(`/patients/${patientId}/adherence/logs`, {
      query: { from, to, page: 1, size },
    }),
};
