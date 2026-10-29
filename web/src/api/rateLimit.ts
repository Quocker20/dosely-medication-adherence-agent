// Xử lý thông báo 429 (Area 4a): khoá đăng nhập theo số điện thoại, giới hạn IP
// của login, và giới hạn chat theo phút/ngày.

import { ApiError } from "./client";

// Thông báo mặc định (tiếng Anh/Việt chung chung) của bộ giới hạn theo cửa sổ:
// "Quá N yêu cầu / Ws cho <scope>." Thông báo có chủ đích (khoá đăng nhập, hết
// lượt chat trong ngày) thì khác và được hiện nguyên văn.
const GENERIC_LIMIT_MESSAGE = /^Quá \d+ yêu cầu/;

export const CHAT_TOO_FAST_MESSAGE = "Bạn gửi quá nhanh, vui lòng thử lại sau ít giây.";

export function retryAfterSeconds(error: ApiError): number | null {
  const errors = error.errors;
  if (!errors || typeof errors !== "object" || Array.isArray(errors)) return null;
  const value = (errors as Record<string, unknown>).retry_after_seconds;
  return typeof value === "number" && Number.isFinite(value) && value > 0 ? Math.ceil(value) : null;
}

function isGenericLimit(error: ApiError): boolean {
  return GENERIC_LIMIT_MESSAGE.test(error.message);
}

export interface LoginRateLimit {
  message: string;
  /** Số giây khoá form (0 nếu server không báo). */
  seconds: number;
}

/** 429 của POST /auth/login -> thông báo + thời gian khoá form; null nếu không phải 429. */
export function loginRateLimit(error: unknown): LoginRateLimit | null {
  if (!(error instanceof ApiError) || error.status !== 429) return null;
  const seconds = retryAfterSeconds(error) ?? 0;
  if (isGenericLimit(error)) {
    return {
      message: `Bạn thao tác quá nhanh, vui lòng thử lại sau ${seconds || 60} giây.`,
      seconds,
    };
  }
  return { message: error.message, seconds };
}

/** Thông báo lỗi cho /chat và /chat/voice. */
export function chatErrorMessage(error: unknown, fallback: string): string {
  if (!(error instanceof ApiError)) return fallback;
  if (error.status === 429 && isGenericLimit(error)) return CHAT_TOO_FAST_MESSAGE;
  return error.message;
}
