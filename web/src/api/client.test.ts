import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { getSession, setSession, type Session } from "../session";
import { refreshAccessToken, request } from "./client";

const USER = { id: "u1", phone: "0900000000", role: "PATIENT" as const, status: "ACTIVE" };

function session(access: string, refresh: string): Session {
  return { accessToken: access, refreshToken: refresh, user: USER, needOnboarding: false };
}

function envelope(data: unknown, status = 200) {
  return new Response(JSON.stringify({ success: status < 400, code: status, message: "m", data }), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function tokens(access: string, refresh: string) {
  return envelope({
    access_token: access,
    refresh_token: refresh,
    token_type: "bearer",
    expires_in: 900,
    must_change_password: false,
    need_onboarding: false,
    user: USER,
  });
}

describe("api client refresh rotation", () => {
  const fetchMock = vi.fn();

  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
    setSession(session("a1", "r1"));
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    setSession(null);
  });

  it("runs one refresh for parallel 401s and persists the rotated refresh token", async () => {
    let refreshCalls = 0;
    fetchMock.mockImplementation(async (url: string, init: RequestInit) => {
      if (url.endsWith("/auth/refresh")) {
        refreshCalls += 1;
        expect(JSON.parse(init.body as string)).toEqual({ refresh_token: "r1" });
        return tokens("a2", "r2");
      }
      const auth = (init.headers as Record<string, string>).Authorization;
      return auth === "Bearer a2" ? envelope({ ok: true }) : envelope(null, 401);
    });

    const results = await Promise.all([request("/x"), request("/y"), request("/z")]);

    expect(results).toEqual([{ ok: true }, { ok: true }, { ok: true }]);
    expect(refreshCalls).toBe(1);
    expect(getSession()?.refreshToken).toBe("r2");
    expect(JSON.parse(window.localStorage.getItem("dosely.portal.session") ?? "{}").refreshToken).toBe("r2");
  });

  it("logs out when refresh answers 401", async () => {
    fetchMock.mockImplementation(async (url: string) =>
      url.endsWith("/auth/refresh") ? envelope(null, 401) : envelope(null, 401),
    );
    await expect(request("/x")).rejects.toMatchObject({ status: 401 });
    expect(getSession()).toBeNull();
  });

  it("keeps the session when refresh fails for a transient reason", async () => {
    fetchMock.mockImplementation(async (url: string) => {
      if (url.endsWith("/auth/refresh")) return envelope(null, 503);
      return envelope(null, 401);
    });
    await expect(request("/x")).rejects.toMatchObject({ status: 401 });
    expect(getSession()?.refreshToken).toBe("r1");

    fetchMock.mockImplementation(async (url: string) => {
      if (url.endsWith("/auth/refresh")) throw new TypeError("network down");
      return envelope(null, 401);
    });
    await expect(request("/x")).rejects.toMatchObject({ status: 401 });
    expect(getSession()?.refreshToken).toBe("r1");
  });

  it("retries without refreshing when another request already rotated the token", async () => {
    fetchMock.mockImplementation(async (url: string, init: RequestInit) => {
      const auth = (init.headers as Record<string, string>).Authorization;
      if (url.endsWith("/slow")) {
        if (auth === "Bearer a1") {
          setSession(session("a2", "r2")); // someone else refreshed while we were in flight
          return envelope(null, 401);
        }
        return envelope({ ok: true });
      }
      throw new Error(`unexpected ${url}`);
    });
    await expect(request("/slow")).resolves.toEqual({ ok: true });
    expect(fetchMock.mock.calls.some(([url]) => String(url).endsWith("/auth/refresh"))).toBe(false);
  });

  it("refreshAccessToken returns the new access token, or null without a session", async () => {
    fetchMock.mockResolvedValue(tokens("a9", "r9"));
    await expect(refreshAccessToken()).resolves.toBe("a9");
    setSession(null);
    await expect(refreshAccessToken()).resolves.toBeNull();
  });
});
