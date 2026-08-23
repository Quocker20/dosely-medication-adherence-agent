// Slice 8: Dashboard
import { request } from "./client";
import type { DashboardPatientDetail, DashboardPatientListItem, PageResponse } from "../types";

export const dashboardApi = {
  dashboardPatients: (params: { page?: number; size?: number; alertStatus?: string; adherenceBand?: string; search?: string } = {}) =>
    request<PageResponse<DashboardPatientListItem>>("/dashboard/patients", {
      query: {
        page: params.page ?? 1,
        size: params.size ?? 50,
        alertStatus: params.alertStatus,
        adherenceBand: params.adherenceBand,
        // Backend đòi search tối thiểu 2 ký tự — gửi chuỗi ngắn hơn sẽ ăn 422.
        search: params.search && params.search.trim().length >= 2 ? params.search.trim() : undefined,
      },
    }),

  dashboardPatientDetail: (patientId: string) =>
    request<DashboardPatientDetail>(`/dashboard/patients/${patientId}`),
};
