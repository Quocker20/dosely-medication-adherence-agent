// Phần lõi HTTP dùng chung cho mọi slice trong src/api/.
// Không chứa endpoint nghiệp vụ nào — endpoint nằm ở các file slice cạnh đây.

import { getSession, sessionFromTokens, setSession } from "../session";
import type { ApiEnvelope, AuthTokenResponse } from "../types";

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

export interface RequestOptions {
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
  const isFormData = options.body instanceof FormData;

  if (options.body !== undefined && !isFormData) headers["Content-Type"] = "application/json";
  const accessToken = options.accessToken ?? session?.accessToken;
  if (!options.anonymous && accessToken) headers.Authorization = `Bearer ${accessToken}`;

  return fetch(buildUrl(path, options.query), {
    method: options.method ?? "GET",
    headers,
    body: options.body === undefined ? undefined : isFormData ? options.body as FormData : JSON.stringify(options.body),
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

export async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
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
