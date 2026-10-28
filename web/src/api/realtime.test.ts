import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { connectRealtime, type RealtimeOptions } from "./realtime";

class FakeSocket {
  static instances: FakeSocket[] = [];
  url: string;
  sent: string[] = [];
  closed = false;
  onopen: (() => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  onclose: ((event: { code: number }) => void) | null = null;
  onerror: (() => void) | null = null;

  constructor(url: string) {
    this.url = url;
    FakeSocket.instances.push(this);
  }
  send(data: string) {
    this.sent.push(data);
  }
  close() {
    this.closed = true;
  }
  // Test helpers
  open() {
    this.onopen?.();
  }
  say(frame: unknown) {
    this.onmessage?.({ data: JSON.stringify(frame) });
  }
  drop(code: number) {
    this.onclose?.({ code });
  }
}

function setup(overrides: Partial<RealtimeOptions> = {}) {
  const options: RealtimeOptions = {
    path: "/ws/dashboard",
    getAccessToken: vi.fn(() => "tok-1"),
    refreshAccessToken: vi.fn(async () => "tok-2"),
    onEvent: vi.fn(),
    onReady: vi.fn(),
    webSocketFactory: (url) => new FakeSocket(url) as unknown as WebSocket,
    ...overrides,
  };
  const stop = connectRealtime(options);
  return { options, stop, socket: () => FakeSocket.instances[FakeSocket.instances.length - 1] };
}

beforeEach(() => {
  FakeSocket.instances = [];
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
});

describe("connectRealtime", () => {
  it("never puts the token in the URL and authenticates with a first message", () => {
    const { socket } = setup();
    expect(socket().url).toMatch(/\/ws\/dashboard$/);
    expect(socket().url).not.toContain("token");
    socket().open();
    expect(socket().sent.map((m) => JSON.parse(m))).toEqual([{ type: "auth", token: "tok-1" }]);
  });

  it("treats the socket as live only after auth_ok and ignores control frames", () => {
    const { socket, options } = setup();
    socket().open();
    socket().say({ event_type: "alert.opened", data: {} });
    expect(options.onEvent).not.toHaveBeenCalled();
    socket().say({ type: "auth_ok", expires_in: 900 });
    expect(options.onReady).toHaveBeenCalledTimes(1);
    socket().say({ type: "pong" });
    socket().say({ event_type: "alert.opened", data: { a: 1 } });
    expect(options.onEvent).toHaveBeenCalledTimes(1);
    expect(options.onEvent).toHaveBeenCalledWith({ event_type: "alert.opened", data: { a: 1 } });
  });

  it("ignores malformed frames", () => {
    const { socket, options } = setup();
    socket().open();
    socket().say({ type: "auth_ok", expires_in: 900 });
    socket().onmessage?.({ data: "not json" });
    expect(options.onEvent).not.toHaveBeenCalled();
  });

  it("re-authenticates with a fresh token before the access token expires", async () => {
    const { socket, options } = setup();
    socket().open();
    socket().say({ type: "auth_ok", expires_in: 900 });
    await vi.advanceTimersByTimeAsync((900 - 60) * 1000 + 1);
    expect(options.refreshAccessToken).toHaveBeenCalledTimes(1);
    expect(socket().sent.map((m) => JSON.parse(m))).toEqual([
      { type: "auth", token: "tok-1" },
      { type: "auth", token: "tok-2" },
    ]);
    expect(FakeSocket.instances).toHaveLength(1);
  });

  it("on 4401 refreshes the token then reconnects", async () => {
    const { socket, options } = setup();
    socket().open();
    socket().drop(4401);
    await vi.advanceTimersByTimeAsync(0);
    expect(options.refreshAccessToken).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(1_000);
    expect(FakeSocket.instances).toHaveLength(2);
  });

  it("stops for good when the session is gone after a 4401", async () => {
    const { socket, options } = setup({
      getAccessToken: vi.fn(() => null),
      refreshAccessToken: vi.fn(async () => null),
    });
    socket().drop(4401);
    await vi.advanceTimersByTimeAsync(120_000);
    expect(options.refreshAccessToken).toHaveBeenCalledTimes(1);
    expect(FakeSocket.instances).toHaveLength(1);
  });

  it("does not reconnect on 4403", async () => {
    const { socket } = setup();
    socket().open();
    socket().drop(4403);
    await vi.advanceTimersByTimeAsync(120_000);
    expect(FakeSocket.instances).toHaveLength(1);
  });

  it("reconnects with exponential backoff and resets after auth_ok", async () => {
    const { socket } = setup();
    socket().drop(1006);
    await vi.advanceTimersByTimeAsync(999);
    expect(FakeSocket.instances).toHaveLength(1);
    await vi.advanceTimersByTimeAsync(1);
    expect(FakeSocket.instances).toHaveLength(2);

    socket().drop(1006); // second failure -> 2 s
    await vi.advanceTimersByTimeAsync(1_999);
    expect(FakeSocket.instances).toHaveLength(2);
    await vi.advanceTimersByTimeAsync(1);
    expect(FakeSocket.instances).toHaveLength(3);

    socket().open();
    socket().say({ type: "auth_ok", expires_in: 900 });
    socket().drop(1006); // success reset the backoff -> 1 s again
    await vi.advanceTimersByTimeAsync(1_000);
    expect(FakeSocket.instances).toHaveLength(4);
  });

  it("caps the backoff delay", async () => {
    const { socket } = setup({ maxDelayMs: 5_000 });
    for (let i = 0; i < 6; i += 1) {
      socket().drop(1006);
      await vi.advanceTimersByTimeAsync(5_000);
    }
    expect(FakeSocket.instances).toHaveLength(7);
  });

  it("closes the socket on error so the backoff path runs", () => {
    const { socket } = setup();
    socket().onerror?.();
    expect(socket().closed).toBe(true);
  });

  it("stop() closes the socket and cancels pending reconnects", async () => {
    const { socket, stop } = setup();
    socket().drop(1006);
    stop();
    await vi.advanceTimersByTimeAsync(120_000);
    expect(FakeSocket.instances).toHaveLength(1);
  });

  it("stop() closes a live socket", () => {
    const { socket, stop } = setup();
    stop();
    expect(socket().closed).toBe(true);
  });
});
