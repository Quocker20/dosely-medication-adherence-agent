// WebSocket realtime dùng chung cho /ws/dashboard và /ws/patient.
//
// Hợp đồng backend (Area 4a): token KHÔNG nằm trên URL. Sau onopen client gửi
// {"type":"auth","token":"<access>"} trong 5 giây và chờ {"type":"auth_ok",
// "expires_in":N} mới coi socket là sống. Close 4401 = chưa xác thực/hết hạn
// (refresh rồi nối lại), 4403 = sai vai trò (dừng hẳn). Khung có `type` là khung
// điều khiển (auth_ok, pong…), khung sự kiện có `event_type`.

import { refreshAccessToken as defaultRefreshAccessToken } from "./client";
import { getSession } from "../session";

export interface RealtimeOptions {
  path: "/ws/dashboard" | "/ws/patient";
  /** Access token hiện hành; null nghĩa là đã đăng xuất. */
  getAccessToken: () => string | null;
  /** Ép refresh phiên, trả access token mới hoặc null nếu không refresh được. */
  refreshAccessToken: () => Promise<string | null>;
  /** Gọi mỗi lần socket vừa xác thực xong (kể cả sau reconnect). */
  onReady?: () => void;
  /** Khung sự kiện (không có `type`). */
  onEvent: (frame: Record<string, unknown>) => void;
  webSocketFactory?: (url: string) => WebSocket;
  baseDelayMs?: number;
  maxDelayMs?: number;
}

const REAUTH_MARGIN_S = 60;
const MIN_REAUTH_S = 5;

function buildUrl(path: string): string {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  // Vercel không proxy WebSocket; deploy tách domain thì nối thẳng backend qua VITE_WS_HOST.
  const wsHost = import.meta.env.VITE_WS_HOST || window.location.host;
  return `${protocol}//${wsHost}${path}`;
}

/** Mở kết nối realtime tự xác thực + tự nối lại; trả hàm dừng. */
export function connectRealtime(options: RealtimeOptions): () => void {
  const baseDelay = options.baseDelayMs ?? 1_000;
  const maxDelay = options.maxDelayMs ?? 30_000;
  const create = options.webSocketFactory ?? ((url: string) => new WebSocket(url));

  let stopped = false;
  let socket: WebSocket | null = null;
  let attempt = 0;
  let retryTimer: number | undefined;
  let reauthTimer: number | undefined;
  // Socket nào đã nhận auth_ok; sự kiện đến trước đó bị bỏ.
  const authed = new WeakSet<WebSocket>();

  function clearReauth() {
    if (reauthTimer !== undefined) window.clearTimeout(reauthTimer);
    reauthTimer = undefined;
  }

  function scheduleReconnect() {
    if (stopped) return;
    const delay = Math.min(baseDelay * 2 ** attempt, maxDelay);
    attempt += 1;
    retryTimer = window.setTimeout(connect, delay);
  }

  function sendAuth(target: WebSocket, token: string) {
    target.send(JSON.stringify({ type: "auth", token }));
  }

  function scheduleReauth(current: WebSocket, expiresIn: number) {
    clearReauth();
    const seconds = Math.max(expiresIn - REAUTH_MARGIN_S, MIN_REAUTH_S);
    reauthTimer = window.setTimeout(async () => {
      const token = await options.refreshAccessToken().catch(() => null);
      if (stopped || socket !== current) return;
      if (token) sendAuth(current, token);
      else current.close(); // onclose: dừng nếu hết phiên, ngược lại backoff
    }, seconds * 1_000);
  }

  function connect() {
    retryTimer = undefined;
    if (stopped) return;
    let current: WebSocket;
    try {
      current = create(buildUrl(options.path));
    } catch {
      scheduleReconnect();
      return;
    }
    socket = current;

    current.onopen = () => {
      const token = options.getAccessToken();
      if (!token) {
        current.close();
        return;
      }
      sendAuth(current, token);
    };

    current.onmessage = (event: MessageEvent) => {
      let frame: Record<string, unknown>;
      try {
        frame = JSON.parse(event.data as string) as Record<string, unknown>;
      } catch {
        return; // Khung hỏng: REST vẫn là nguồn chính xác.
      }
      if (!frame || typeof frame !== "object") return;
      if (typeof frame.type === "string") {
        if (frame.type === "auth_ok") {
          authed.add(current);
          attempt = 0;
          const expiresIn = typeof frame.expires_in === "number" ? frame.expires_in : 0;
          if (expiresIn > 0) scheduleReauth(current, expiresIn);
          options.onReady?.();
        }
        return; // pong và các type lạ: bỏ qua.
      }
      if (!authed.has(current)) return;
      options.onEvent(frame);
    };

    current.onerror = () => {
      // Trình duyệt luôn bắn close sau error; đóng chủ động để đi chung nhánh backoff.
      current.close();
    };

    current.onclose = (event: CloseEvent) => {
      if (socket !== current) return;
      socket = null;
      clearReauth();
      if (stopped) return;
      if (event.code === 4403) {
        stopped = true; // Sai vai trò: thử lại cũng vô ích.
        return;
      }
      if (event.code === 4401) {
        void options
          .refreshAccessToken()
          .catch(() => null)
          .then((token) => {
            if (stopped) return;
            if (!token && !options.getAccessToken()) {
              stopped = true; // Phiên đã mất — App đưa người dùng về đăng nhập.
              return;
            }
            scheduleReconnect();
          });
        return;
      }
      scheduleReconnect();
    };
  }

  connect();

  return () => {
    stopped = true;
    if (retryTimer !== undefined) window.clearTimeout(retryTimer);
    retryTimer = undefined;
    clearReauth();
    const current = socket;
    socket = null;
    current?.close();
  };
}

/** Cấu hình mặc định cho web: lấy token từ phiên hiện tại. */
export function connectSessionRealtime(
  path: RealtimeOptions["path"],
  handlers: Pick<RealtimeOptions, "onEvent" | "onReady">,
  fallbackToken?: string,
): () => void {
  return connectRealtime({
    path,
    getAccessToken: () => getSession()?.accessToken ?? fallbackToken ?? null,
    refreshAccessToken: defaultRefreshAccessToken,
    ...handlers,
  });
}
