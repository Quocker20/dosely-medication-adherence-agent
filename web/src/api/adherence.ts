import { request } from "./client";
import type { AdherenceLog, AdherenceReviewDetail, AdherenceSummary, PageResponse } from "../types";

export const adherenceApi = {
  adherenceSummary: (patientId: string, from: string, to: string) =>
    request<AdherenceSummary>(`/patients/${patientId}/adherence`, { query: { from, to } }),
  adherenceLogs: (patientId: string, from: string, to: string, size = 20) =>
    request<PageResponse<AdherenceLog>>(`/patients/${patientId}/adherence/logs`, {
      query: { from, to, page: 1, size },
    }),
  adherenceReviews: (patientId: string, page = 1, size = 10) =>
    request<PageResponse<AdherenceReviewDetail>>(`/patients/${patientId}/adherence-reviews`, {
      query: { page, size },
    }),
};

