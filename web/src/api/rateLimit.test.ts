import { describe, expect, it } from "vitest";

import { ApiError } from "./client";
import { chatErrorMessage, loginRateLimit, retryAfterSeconds } from "./rateLimit";

const DAILY = "Bạn đã dùng hết lượt hỏi trợ lý hôm nay, vui lòng quay lại vào ngày mai.";
const LOCK = "Bạn đã nhập sai quá nhiều lần. Vui lòng thử lại sau 15 phút.";

describe("rate limit helpers", () => {
  it("reads retry_after_seconds from the error body", () => {
    expect(retryAfterSeconds(new ApiError(429, "x", { retry_after_seconds: 42 }))).toBe(42);
    expect(retryAfterSeconds(new ApiError(429, "x", null))).toBeNull();
    expect(retryAfterSeconds(new ApiError(429, "x", [{ msg: "a" }]))).toBeNull();
  });

  it("login lockout: shows the server message and locks the form for retry_after_seconds", () => {
    const result = loginRateLimit(new ApiError(429, LOCK, { retry_after_seconds: 900 }));
    expect(result).toEqual({ message: LOCK, seconds: 900 });
  });

  it("login per-IP limit: own Vietnamese text instead of the generic English one", () => {
    const result = loginRateLimit(
      new ApiError(429, "Quá 10 yêu cầu / 60s cho login.", { retry_after_seconds: 30 }),
    );
    expect(result?.seconds).toBe(30);
    expect(result?.message).toMatch(/quá nhanh/);
    expect(result?.message).not.toContain("yêu cầu / 60s");
  });

  it("login helper ignores non-429 errors", () => {
    expect(loginRateLimit(new ApiError(401, "Invalid", null))).toBeNull();
  });

  it("chat: daily-limit message is shown verbatim", () => {
    expect(chatErrorMessage(new ApiError(429, DAILY, { retry_after_seconds: 3600 }), "fb")).toBe(DAILY);
  });

  it("chat: per-minute 429 gets the slow-down text", () => {
    expect(
      chatErrorMessage(new ApiError(429, "Quá 20 yêu cầu / 60s cho chat.", { retry_after_seconds: 12 }), "fb"),
    ).toBe("Bạn gửi quá nhanh, vui lòng thử lại sau ít giây.");
  });

  it("chat: other errors use their message, or the fallback for unknown errors", () => {
    expect(chatErrorMessage(new ApiError(500, "boom", null), "fb")).toBe("boom");
    expect(chatErrorMessage(new Error("x"), "fb")).toBe("fb");
  });
});
