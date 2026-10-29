import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "../../api/client";
import LoginScreen from "./LoginScreen";

const { loginMock } = vi.hoisted(() => ({ loginMock: vi.fn() }));

vi.mock("../../api", async () => ({
  api: { login: loginMock, changePassword: vi.fn() },
  ApiError: (await import("../../api/client")).ApiError,
}));

const LOCK = "Bạn đã nhập sai quá nhiều lần. Vui lòng thử lại sau 1 phút.";

describe("LoginScreen 429 handling", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    loginMock.mockReset();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  async function clickDemo() {
    fireEvent.click(screen.getByRole("button", { name: "0830000001" }));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(500);
    });
  }

  it("shows the server lockout message and disables login until the countdown ends", async () => {
    loginMock.mockRejectedValue(new ApiError(429, LOCK, { retry_after_seconds: 3 }));
    render(<LoginScreen onBack={() => {}} />);

    await clickDemo();

    expect(screen.getByText(LOCK)).toBeInTheDocument();
    expect(screen.getByText(/Có thể thử lại sau 0:03/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "0830000001" })).toBeDisabled();
    expect(screen.getByRole("button", { name: /Tiếp tục/ })).toBeDisabled();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1_000);
    });
    expect(screen.getByText(/Có thể thử lại sau 0:02/)).toBeInTheDocument();

    // Each tick re-renders and re-arms the timer, so step one second per act.
    for (let i = 0; i < 2; i += 1) {
      await act(async () => {
        await vi.advanceTimersByTimeAsync(1_000);
      });
    }
    expect(screen.queryByText(/Có thể thử lại sau/)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "0830000001" })).toBeEnabled();
    expect(screen.getByRole("button", { name: /Tiếp tục/ })).toBeEnabled();
  });

  it("uses its own Vietnamese text for the per-IP limiter", async () => {
    loginMock.mockRejectedValue(
      new ApiError(429, "Quá 10 yêu cầu / 60s cho login.", { retry_after_seconds: 20 }),
    );
    render(<LoginScreen onBack={() => {}} />);

    await clickDemo();

    expect(screen.getByText(/Bạn thao tác quá nhanh/)).toBeInTheDocument();
    expect(screen.queryByText(/yêu cầu \/ 60s/)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "0830000001" })).toBeDisabled();
  });
});
