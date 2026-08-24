// Admin: doctor management & audit logs
import { request } from "./client";
import type {
  AuditLog,
  CreateDoctorRequest,
  CreateDoctorResponse,
  DoctorDetail,
  PageResponse,
  UpdateDoctorRequest,
} from "../types";

export const adminApi = {
  adminDoctors: (params: { page?: number; size?: number; search?: string } = {}) =>
    request<PageResponse<DoctorDetail>>("/admin/doctors", {
      query: {
        page: params.page ?? 1,
        size: params.size ?? 10,
        search: params.search?.trim() || undefined,
      },
    }),

  adminDoctor: (doctorId: string) => request<DoctorDetail>(`/admin/doctors/${doctorId}`),

  createDoctor: (payload: CreateDoctorRequest) =>
    request<CreateDoctorResponse>("/admin/doctors", {
      method: "POST",
      body: payload,
    }),

  updateDoctor: (doctorId: string, payload: UpdateDoctorRequest) =>
    request<DoctorDetail>(`/admin/doctors/${doctorId}`, {
      method: "PUT",
      body: payload,
    }),

  deactivateDoctor: (doctorId: string) =>
    request<null>(`/admin/doctors/${doctorId}`, { method: "DELETE" }),

  adminAuditLogs: (params: {
    page?: number;
    size?: number;
    actorId?: string;
    entityType?: string;
  } = {}) =>
    request<PageResponse<AuditLog>>("/admin/audit-logs", {
      query: {
        page: params.page ?? 1,
        size: params.size ?? 10,
        actorId: params.actorId || undefined,
        entityType: params.entityType || undefined,
      },
    }),
};
