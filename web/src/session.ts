import type { AuthTokenResponse, UserResponse } from "./types";

/**
 * Phiên đăng nhập của portal bác sĩ.
 *
 * Token nằm trong localStorage: SPA thuần không có backend-for-frontend nên
 * không dùng được cookie HttpOnly. Đánh đổi ở đây là token đọc được bằng JS,
 * nên bất kỳ lỗ hổng XSS nào cũng lộ token — giữ thời hạn access token ngắn
 * và đừng render HTML thô từ dữ liệu API.
 */

const STORAGE_KEY = "dosely.portal.session";

export interface Session {
  accessToken: string;
  refreshToken: string;
  user: UserResponse;
  /** PATIENT-only onboarding gate; kept in sync on every login/refresh (Slice 1). */
  needOnboarding: boolean;
}

type Listener = (session: Session | null) => void;

const listeners = new Set<Listener>();
let current: Session | null = readFromStorage();

function readFromStorage(): Session | null {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<Session>;
    if (!parsed.accessToken || !parsed.refreshToken || !parsed.user) return null;
    return parsed as Session;
  } catch {
    // localStorage bị chặn hoặc JSON hỏng — coi như chưa đăng nhập.
    return null;
  }
}

function writeToStorage(session: Session | null) {
  try {
    if (session) window.localStorage.setItem(STORAGE_KEY, JSON.stringify(session));
    else window.localStorage.removeItem(STORAGE_KEY);
  } catch {
    // Không ghi được thì phiên chỉ sống trong tab hiện tại, không phải lỗi chặn luồng.
  }
}

export function getSession(): Session | null {
  return current;
}

export function setSession(session: Session | null) {
  current = session;
  writeToStorage(session);
  listeners.forEach((listener) => listener(session));
}

/** Lưu kết quả /auth/login hoặc /auth/refresh thành phiên hiện tại. */
export function sessionFromTokens(tokens: AuthTokenResponse): Session {
  return {
    accessToken: tokens.access_token,
    refreshToken: tokens.refresh_token,
    user: tokens.user,
    needOnboarding: tokens.need_onboarding,
  };
}

export function subscribe(listener: Listener): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}
