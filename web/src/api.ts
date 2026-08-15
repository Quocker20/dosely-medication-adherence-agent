import { getSession, sessionFromTokens, setSession } from "./session";
import type {
  ActiveSchedule,
  AdherenceSummary,
  AgentRunAsyncResponse,
  AgentRunStatus,
  AlertDetail,
  ApiEnvelope,
  AuthTokenResponse,
  CreatePrescriptionRequest,
  CreatePrescriptionResponse,
  DashboardPatientDetail,
  DashboardPatientListItem,
  MedicationDetail,
  PageResponse,
  PatientRoutine,
  PrescriptionDetail,
  PrescriptionItemDetail,
  PrescriptionItemIn,
} from "./types";

const BASE = "/api/v1";

/** Lỗi có cấu trúc từ API — giữ nguyên phần errors của envelope để hiện chi tiết. */
export class ApiError extends Error {
  status: number;
  errors: unknown;

  constructor(status: number, message: string, errors: unknown = null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.errors = errors;
  }

  /**
   * Danh sách message đọc được từ `errors`. FastAPI RequestValidationError trả
   * mảng {loc, msg, type}; AppException trả bất kỳ thứ gì service ném ra.
   */
  get details(): string[] {
    if (!Array.isArray(this.errors)) return [];
    return this.errors.map((item) => {
      if (typeof item === "string") return item;
      if (item && typeof item === "object") {
        const record = item as Record<string, unknown>;
        const loc = Array.isArray(record.loc) ? record.loc.join(".") : null;
        const msg = typeof record.msg === "string" ? record.msg : JSON.stringify(item);
        return loc ? `${loc}: ${msg}` : msg;
      }
      return String(item);
    });
  }
}

interface RequestOptions {
  method?: string;
  body?: unknown;
  query?: Record<string, string | number | boolean | null | undefined>;
  headers?: Record<string, string>;
  /** Access token used by first-login PIN change before the session is committed. */
  accessToken?: string | null;
  /** Endpoint công khai (login/refresh) — không gắn Authorization, không tự refresh. */
  anonymous?: boolean;
}

function buildUrl(path: string, query?: RequestOptions["query"]): string {
  if (!query) return `${BASE}${path}`;
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value === null || value === undefined || value === "") continue;
    params.append(key, String(value));
  }
  const qs = params.toString();
  return qs ? `${BASE}${path}?${qs}` : `${BASE}${path}`;
}

/**
 * Bóc envelope APIResponse. Lỗi cũng trả envelope nên message lấy được ở cả
 * hai nhánh; chỉ khi body không phải JSON mới phải chế message theo status.
 */
async function unwrap<T>(response: Response): Promise<T> {
  let envelope: ApiEnvelope<T> | null = null;
  try {
    envelope = (await response.json()) as ApiEnvelope<T>;
  } catch {
    envelope = null;
  }

  if (!response.ok) {
    throw new ApiError(
      response.status,
      envelope?.message ?? `Lỗi ${response.status}`,
      envelope?.errors ?? null,
    );
  }

  if (!envelope) {
    throw new ApiError(response.status, "Phản hồi không phải JSON hợp lệ");
  }

  // 200 nhưng success=false không nên xảy ra; nếu có thì đừng nuốt lặng.
  if (envelope.success === false) {
    throw new ApiError(envelope.code ?? response.status, envelope.message, envelope.errors ?? null);
  }

  return envelope.data as T;
}

async function rawRequest(path: string, options: RequestOptions): Promise<Response> {
  const session = getSession();
  const headers: Record<string, string> = { ...(options.headers ?? {}) };

  if (options.body !== undefined) headers["Content-Type"] = "application/json";
  const accessToken = options.accessToken ?? session?.accessToken;
  if (!options.anonymous && accessToken) headers.Authorization = `Bearer ${accessToken}`;

  return fetch(buildUrl(path, options.query), {
    method: options.method ?? "GET",
    headers,
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
  });
}

/**
 * Một lần refresh dùng chung cho mọi request đang chờ. Không có single-flight
 * thì 4 call song song cùng dính 401 sẽ bắn 4 lần /auth/refresh, và refresh
 * token xoay vòng khiến 3 trong số đó tự huỷ phiên vừa cấp.
 */
let refreshInFlight: Promise<boolean> | null = null;

async function refreshSession(): Promise<boolean> {
  const session = getSession();
  if (!session) return false;

  if (!refreshInFlight) {
    refreshInFlight = (async () => {
      try {
        const response = await rawRequest("/auth/refresh", {
          method: "POST",
          body: { refresh_token: session.refreshToken },
          anonymous: true,
        });
        if (!response.ok) {
          setSession(null);
          return false;
        }
        const tokens = await unwrap<AuthTokenResponse>(response);
        setSession(sessionFromTokens(tokens));
        return true;
      } catch {
        setSession(null);
        return false;
      } finally {
        refreshInFlight = null;
      }
    })();
  }

  return refreshInFlight;
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  let response = await rawRequest(path, options);

  if (response.status === 401 && !options.anonymous && getSession()) {
    const refreshed = await refreshSession();
    if (!refreshed) {
      throw new ApiError(401, "Phiên đăng nhập đã hết hạn, vui lòng đăng nhập lại");
    }
    response = await rawRequest(path, options);
  }

  return unwrap<T>(response);
}

export const api = {
  // ---- Slice 1: Authentication -------------------------------------------
  login: (phone: string, password: string) =>
    request<AuthTokenResponse>("/auth/login", {
      method: "POST",
      body: { phone, password },
      anonymous: true,
    }),

  logout: (refreshToken: string) =>
    request<null>("/auth/logout", { method: "POST", body: { refresh_token: refreshToken } }),

  changePassword: (currentPassword: string, newPassword: string, accessToken?: string) =>
    request<null>("/auth/change-password", {
      method: "POST",
      body: { current_password: currentPassword, new_password: newPassword },
      accessToken,
    }),

  // ---- Slice 8: Dashboard -------------------------------------------------
  dashboardPatients: (params: { page?: number; size?: number; alertStatus?: string; search?: string } = {}) =>
    request<PageResponse<DashboardPatientListItem>>("/dashboard/patients", {
      query: {
        page: params.page ?? 1,
        size: params.size ?? 50,
        alertStatus: params.alertStatus,
        // Backend đòi search tối thiểu 2 ký tự — gửi chuỗi ngắn hơn sẽ ăn 422.
        search: params.search && params.search.trim().length >= 2 ? params.search.trim() : undefined,
      },
    }),

  dashboardPatientDetail: (patientId: string) =>
    request<DashboardPatientDetail>(`/dashboard/patients/${patientId}`),

  // ---- Slice 7: Alerts ----------------------------------------------------
  alerts: (params: { status?: string; patientId?: string; page?: number; size?: number } = {}) =>
    request<PageResponse<AlertDetail>>("/alerts", {
      query: {
        status: params.status,
        patientId: params.patientId,
        page: params.page ?? 1,
        size: params.size ?? 50,
      },
    }),

  acknowledgeAlert: (alertId: string) =>
    request<AlertDetail>(`/alerts/${alertId}/acknowledge`, { method: "POST" }),

  resolveAlert: (alertId: string, resolutionNote: string) =>
    request<AlertDetail>(`/alerts/${alertId}/resolve`, {
      method: "POST",
      body: { resolution_note: resolutionNote },
    }),

  /** from/to là bắt buộc phía backend (Query(...) không default) — dạng YYYY-MM-DD. */
  adherenceSummary: (patientId: string, from: string, to: string) =>
    request<AdherenceSummary>(`/patients/${patientId}/adherence`, { query: { from, to } }),

  // ---- Slice 4: Patient routine ------------------------------------------
  patientRoutine: (patientId: string) => request<PatientRoutine>(`/patients/${patientId}/routine`),

  // ---- Slice 3: Medications ----------------------------------------------
  medications: (params: { page?: number; size?: number; search?: string } = {}) =>
    request<PageResponse<MedicationDetail>>("/medications", {
      query: {
        page: params.page ?? 1,
        size: params.size ?? 100,
        search: params.search && params.search.trim().length >= 2 ? params.search.trim() : undefined,
      },
    }),

  medication: (medicationId: string) => request<MedicationDetail>(`/medications/${medicationId}`),

  // ---- Slice 5: Prescriptions --------------------------------------------
  /** Bệnh nhân được xác định bằng số điện thoại (find-or-create), không phải patient_id. */
  createPrescription: (payload: CreatePrescriptionRequest) =>
    request<CreatePrescriptionResponse>("/prescriptions", { method: "POST", body: payload }),

  prescription: (prescriptionId: string) =>
    request<PrescriptionDetail>(`/prescriptions/${prescriptionId}`),

  patientPrescriptions: (patientId: string, params: { status?: string; page?: number; size?: number } = {}) =>
    request<PageResponse<PrescriptionDetail>>(`/patients/${patientId}/prescriptions`, {
      query: { status: params.status, page: params.page ?? 1, size: params.size ?? 20 },
    }),

  updatePrescription: (prescriptionId: string, diagnosisNote: string | null) =>
    request<PrescriptionDetail>(`/prescriptions/${prescriptionId}`, {
      method: "PUT",
      body: { diagnosis_note: diagnosisNote },
    }),

  approvePrescription: (prescriptionId: string) =>
    request<PrescriptionDetail>(`/prescriptions/${prescriptionId}/approve`, { method: "POST" }),

  cancelPrescription: (prescriptionId: string, cancelReason: string) =>
    request<PrescriptionDetail>(`/prescriptions/${prescriptionId}/cancel`, {
      method: "POST",
      body: { cancel_reason: cancelReason },
    }),

  addPrescriptionItem: (prescriptionId: string, item: PrescriptionItemIn) =>
    request<PrescriptionItemDetail>(`/prescriptions/${prescriptionId}/items`, {
      method: "POST",
      body: item,
    }),

  updatePrescriptionItem: (prescriptionId: string, itemId: string, item: PrescriptionItemIn) =>
    request<PrescriptionItemDetail>(`/prescriptions/${prescriptionId}/items/${itemId}`, {
      method: "PUT",
      body: item,
    }),

  deletePrescriptionItem: (prescriptionId: string, itemId: string) =>
    request<null>(`/prescriptions/${prescriptionId}/items/${itemId}`, { method: "DELETE" }),

  // ---- Slice 6: Schedules & Agents ---------------------------------------
  /** 202 Accepted — trả agent_run_id, phải poll agentRun() để biết kết quả. */
  generateSchedule: (patientId: string, reason?: string) =>
    request<AgentRunAsyncResponse>(`/patients/${patientId}/schedules/generate`, {
      method: "POST",
      body: { reason: reason ?? null },
    }),

  schedule: (patientId: string, date?: string) =>
    request<ActiveSchedule>(`/patients/${patientId}/schedules`, { query: { date } }),

  agentRun: (agentRunId: string) => request<AgentRunStatus>(`/agent-runs/${agentRunId}`),

  // ---- Admin --------------------------------------------------------------
  adminDoctors: (params: { page?: number; size?: number; search?: string } = {}) =>
    request<PageResponse<import("./types").DoctorDetail>>("/admin/doctors", {
      query: {
        page: params.page ?? 1,
        size: params.size ?? 10,
        search: params.search?.trim() || undefined,
      },
    }),

  adminDoctor: (doctorId: string) =>
    request<import("./types").DoctorDetail>(`/admin/doctors/${doctorId}`),

  createDoctor: (payload: import("./types").CreateDoctorRequest) =>
    request<import("./types").CreateDoctorResponse>("/admin/doctors", {
      method: "POST",
      body: payload,
    }),

  updateDoctor: (doctorId: string, payload: import("./types").UpdateDoctorRequest) =>
    request<import("./types").DoctorDetail>(`/admin/doctors/${doctorId}`, {
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
    request<PageResponse<import("./types").AuditLog>>("/admin/audit-logs", {
      query: {
        page: params.page ?? 1,
        size: params.size ?? 10,
        actorId: params.actorId || undefined,
        entityType: params.entityType || undefined,
      },
    }),
};

/**
 * Chờ Planning Agent chạy xong. Agent chạy nền (202) nên không có
 * cách nào lấy lịch ngay trong response — phải poll agent run tới trạng thái
 * cuối. SLO của agent là < 10s; mặc định bỏ cuộc sau ~30s để UI không treo.
 */
export async function waitForAgentRun(
  agentRunId: string,
  options: { intervalMs?: number; timeoutMs?: number } = {},
): Promise<AgentRunStatus> {
  const interval = options.intervalMs ?? 1000;
  const timeout = options.timeoutMs ?? 30_000;
  const startedAt = Date.now();

  // agent_runs.status chỉ ghi RUNNING -> COMPLETED | FAILED
  // (src/modules/agents/repository.py) — không có SUCCESS/NEEDS_REVIEW ở tầng này.
  const terminal = new Set(["COMPLETED", "FAILED"]);

  for (;;) {
    const run = await api.agentRun(agentRunId);
    if (terminal.has(run.status.toUpperCase())) return run;
    if (Date.now() - startedAt > timeout) return run;
    await new Promise((resolve) => setTimeout(resolve, interval));
  }
}
