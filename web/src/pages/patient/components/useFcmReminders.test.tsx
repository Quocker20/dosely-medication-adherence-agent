import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useFcmReminders } from "./useFcmReminders";

const { registerDeviceTokenMock, onMessageMock, getTokenMock, getMessagingIfSupportedMock } = vi.hoisted(() => ({
  registerDeviceTokenMock: vi.fn(),
  onMessageMock: vi.fn(),
  getTokenMock: vi.fn(),
  getMessagingIfSupportedMock: vi.fn(),
}));

vi.mock("../../../api", () => ({
  api: {
    registerDeviceToken: registerDeviceTokenMock,
  },
}));

vi.mock("../../../firebase", () => ({
  FIREBASE_VAPID_KEY: "test-vapid-key",
  getMessagingIfSupported: getMessagingIfSupportedMock,
}));

vi.mock("firebase/messaging", () => ({
  getToken: getTokenMock,
  onMessage: onMessageMock,
  isSupported: vi.fn().mockResolvedValue(true),
}));

describe("useFcmReminders", () => {
  let messageHandler: ((payload: unknown) => void) | null = null;

  beforeEach(() => {
    window.localStorage.clear();
    window.sessionStorage.clear();
    registerDeviceTokenMock.mockReset().mockResolvedValue(null);
    getTokenMock.mockReset().mockResolvedValue("mock-fcm-token-123");
    getMessagingIfSupportedMock.mockReset().mockResolvedValue({ app: {} });

    messageHandler = null;
    onMessageMock.mockReset().mockImplementation((_messaging, handler) => {
      messageHandler = handler;
      return () => {
        messageHandler = null;
      };
    });

    // Mock Notification API
    vi.stubGlobal("Notification", {
      permission: "default",
      requestPermission: vi.fn().mockResolvedValue("granted"),
    });

    // Mock ServiceWorker in navigator
    Object.defineProperty(navigator, "serviceWorker", {
      value: {
        register: vi.fn().mockResolvedValue({ scope: "/" }),
      },
      configurable: true,
    });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("initializes with empty active reminders and zero unread count", () => {
    const { result } = renderHook(() => useFcmReminders("patient-1", "token-abc"));

    expect(result.current.active).toEqual([]);
    expect(result.current.history).toEqual([]);
    expect(result.current.unreadCount).toBe(0);
  });

  it("loads stored history from localStorage on mount", () => {
    const saved = [
      {
        id: "prev-1",
        title: "Uống thuốc sáng",
        body: "Aspirin 81mg",
        firedAt: "2026-08-30T07:00:00.000Z",
        read: false,
      },
    ];
    window.localStorage.setItem("remindrx_notif_history_patient-1", JSON.stringify(saved));

    const { result } = renderHook(() => useFcmReminders("patient-1", "token-abc"));

    expect(result.current.history).toHaveLength(1);
    expect(result.current.history[0].id).toBe("prev-1");
    expect(result.current.unreadCount).toBe(1);
  });

  it("adds foreground push message to active stack and history", async () => {
    const { result } = renderHook(() => useFcmReminders("patient-1", "token-abc"));

    // Wait for getMessagingIfSupported to resolve
    await act(async () => {
      await Promise.resolve();
    });

    expect(onMessageMock).toHaveBeenCalled();
    expect(messageHandler).not.toBeNull();

    act(() => {
      messageHandler?.({
        messageId: "msg-1",
        notification: {
          title: "Đến giờ uống thuốc",
          body: "Metformin 500mg (1 viên)",
        },
      });
    });

    expect(result.current.active).toHaveLength(1);
    expect(result.current.active[0].title).toBe("Đến giờ uống thuốc");
    expect(result.current.active[0].body).toBe("Metformin 500mg (1 viên)");
    expect(result.current.history).toHaveLength(1);
    expect(result.current.unreadCount).toBe(1);
  });

  it("uses data payload fields when notification payload is absent", async () => {
    const { result } = renderHook(() => useFcmReminders("patient-1", "token-abc"));

    await act(async () => {
      await Promise.resolve();
    });

    act(() => {
      messageHandler?.({
        messageId: "msg-data-only",
        data: {
          title: "Nhắc thuốc buổi tối",
          body: "Uống Atorvastatin sau ăn tối",
        },
      });
    });

    expect(result.current.active[0]).toMatchObject({
      id: "msg-data-only",
      title: "Nhắc thuốc buổi tối",
      body: "Uống Atorvastatin sau ăn tối",
      read: false,
    });
  });

  it("dismisses active reminder without removing it from history", async () => {
    const { result } = renderHook(() => useFcmReminders("patient-1", "token-abc"));

    await act(async () => {
      await Promise.resolve();
    });

    act(() => {
      messageHandler?.({
        messageId: "msg-1",
        notification: {
          title: "Đến giờ uống thuốc",
          body: "Metformin 500mg",
        },
      });
    });

    expect(result.current.active).toHaveLength(1);

    act(() => {
      result.current.dismiss("msg-1");
    });

    expect(result.current.active).toHaveLength(0);
    expect(result.current.history).toHaveLength(1);
  });

  it("marks all notifications as read and resets unreadCount", async () => {
    const { result } = renderHook(() => useFcmReminders("patient-1", "token-abc"));

    await act(async () => {
      await Promise.resolve();
    });

    act(() => {
      messageHandler?.({
        messageId: "msg-1",
        notification: {
          title: "Đến giờ uống thuốc",
          body: "Metformin 500mg",
        },
      });
    });

    expect(result.current.unreadCount).toBe(1);

    act(() => {
      result.current.markAllRead();
    });

    expect(result.current.unreadCount).toBe(0);
    expect(result.current.history[0].read).toBe(true);
  });

  it("requests permission and registers device token with backend", async () => {
    const { result } = renderHook(() => useFcmReminders("patient-1", "token-abc"));

    await act(async () => {
      await result.current.requestPermissionAndRegister();
    });

    expect(Notification.requestPermission).toHaveBeenCalled();
    expect(navigator.serviceWorker.register).toHaveBeenCalledWith("/firebase-messaging-sw.js");
    expect(getTokenMock).toHaveBeenCalled();
    expect(registerDeviceTokenMock).toHaveBeenCalledWith(
      "mock-fcm-token-123",
      expect.stringContaining("web-"),
      "token-abc",
    );
  });

  it("does not register a device token when notification permission is denied", async () => {
    vi.stubGlobal("Notification", {
      permission: "default",
      requestPermission: vi.fn().mockResolvedValue("denied"),
    });

    const { result } = renderHook(() => useFcmReminders("patient-1", "token-abc"));

    await act(async () => {
      await result.current.requestPermissionAndRegister();
    });

    expect(Notification.requestPermission).toHaveBeenCalled();
    expect(navigator.serviceWorker.register).not.toHaveBeenCalled();
    expect(getTokenMock).not.toHaveBeenCalled();
    expect(registerDeviceTokenMock).not.toHaveBeenCalled();
  });

  it("does not call backend again for the same token during the same session", async () => {
    const { result } = renderHook(() => useFcmReminders("patient-1", "token-abc"));

    await act(async () => {
      await result.current.requestPermissionAndRegister();
      await result.current.requestPermissionAndRegister();
    });

    expect(getTokenMock).toHaveBeenCalledTimes(2);
    expect(registerDeviceTokenMock).toHaveBeenCalledTimes(1);
  });

  it("unsubscribes from foreground messages on unmount", async () => {
    const { unmount } = renderHook(() => useFcmReminders("patient-1", "token-abc"));

    await act(async () => {
      await Promise.resolve();
    });

    expect(messageHandler).not.toBeNull();

    unmount();

    expect(messageHandler).toBeNull();
  });
});
