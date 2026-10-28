import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { setSession } from "../session";
import { authApi } from "./auth";

describe("authApi.logout", () => {
  const fetchMock = vi.fn();

  beforeEach(() => {
    fetchMock.mockReset().mockResolvedValue(
      new Response(JSON.stringify({ success: true, code: 200, message: "ok", data: null }), { status: 200 }),
    );
    vi.stubGlobal("fetch", fetchMock);
    setSession({
      accessToken: "a",
      refreshToken: "r",
      user: { id: "u", phone: "0", role: "PATIENT", status: "ACTIVE" },
      needOnboarding: false,
    });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    setSession(null);
  });

  it("sends the refresh token and this device's FCM token", async () => {
    await authApi.logout("r", "fcm-1");
    const [, init] = fetchMock.mock.calls[0];
    expect(JSON.parse(init.body)).toEqual({ refresh_token: "r", fcm_token: "fcm-1" });
  });

  it("omits fcm_token when the device has none", async () => {
    await authApi.logout("r");
    const [, init] = fetchMock.mock.calls[0];
    expect(JSON.parse(init.body)).toEqual({ refresh_token: "r" });
  });

  it("treats 403 (token owned by someone else) as logged out locally without throwing", async () => {
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ success: false, code: 403, message: "no", data: null }), { status: 403 }),
    );
    await expect(authApi.logout("r")).resolves.toBeUndefined();
  });
});
