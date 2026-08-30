import { request } from "./client";
import type { PageResponse, SuspectedAdverseEvent } from "../types";
export const adverseEventsApi = {
  adverseEvents: (params: { status?: string; risk?: string; page?: number; size?: number } = {}) =>
    request<PageResponse<SuspectedAdverseEvent>>("/adverse-events", { query: { ...params, page: params.page ?? 1, size: params.size ?? 50 } }),
  reviewAdverseEvent: (id: string, causality: string, clinicianNote: string) =>
    request<SuspectedAdverseEvent>(`/adverse-events/${id}/review`, { method: "POST", body: { causality, clinician_note: clinicianNote } }),
};
