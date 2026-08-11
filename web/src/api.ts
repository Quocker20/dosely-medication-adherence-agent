import type {
  Alert,
  AlertState,
  DashboardSummary,
  DrugCatalogEntry,
  MedicationSchedule,
  Patient,
  PatientDetail,
  Prescription,
  PrescriptionItemIn,
  ValidationIssue,
} from "./types";

const BASE = "/api/v1";

/** Lỗi có cấu trúc từ API — giữ nguyên danh sách issue của validator. */
export class ApiError extends Error {
  status: number;
  issues: ValidationIssue[];

  constructor(status: number, message: string, issues: ValidationIssue[] = []) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.issues = issues;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });

  if (!response.ok) {
    let detail: unknown = null;
    try {
      detail = (await response.json()).detail;
    } catch {
      detail = null;
    }

    if (Array.isArray(detail) && detail.length > 0 && typeof detail[0] === "object" && "code" in detail[0]) {
      const issues = detail as ValidationIssue[];
      throw new ApiError(response.status, issues[0].message, issues);
    }
    throw new ApiError(response.status, typeof detail === "string" ? detail : `Lỗi ${response.status}`);
  }

  return (await response.json()) as T;
}

export const api = {
  summary: () => request<DashboardSummary>("/dashboard/summary"),
  patients: () => request<Patient[]>("/dashboard/patients"),
  patientDetail: (id: string) => request<PatientDetail>(`/dashboard/patients/${id}`),
  drugs: () => request<DrugCatalogEntry[]>("/drugs"),

  alerts: (state?: AlertState) => request<Alert[]>(`/alerts${state ? `?state=${state}` : ""}`),
  acknowledgeAlert: (id: string) => request<Alert>(`/alerts/${id}/acknowledge`, { method: "POST" }),
  resolveAlert: (id: string, falsePositive: boolean) =>
    request<Alert>(`/alerts/${id}/resolve`, {
      method: "POST",
      body: JSON.stringify({ false_positive: falsePositive }),
    }),

  createPrescription: (patientId: string, items: PrescriptionItemIn[]) =>
    request<Prescription>(`/patients/${patientId}/prescriptions`, {
      method: "POST",
      body: JSON.stringify({ items }),
    }),
  approvePrescription: (id: string) => request<Prescription>(`/prescriptions/${id}/approve`, { method: "POST" }),
  generateSchedule: (patientId: string, prescriptionId: string) =>
    request<MedicationSchedule>(`/patients/${patientId}/schedules/generate`, {
      method: "POST",
      body: JSON.stringify({ prescription_id: prescriptionId }),
    }),
  schedule: (patientId: string) => request<MedicationSchedule>(`/patients/${patientId}/schedules`),
};
