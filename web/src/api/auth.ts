// Slice 1: Authentication
import { ApiError, request } from "./client";
import type { AuthTokenResponse } from "../types";

export const authApi = {
  login: (phone: string, password: string) =>
    request<AuthTokenResponse>("/auth/login", {
      method: "POST",
      body: { phone, password },
      anonymous: true,
    }),

  refresh: (refreshToken: string) =>
    request<AuthTokenResponse>("/auth/refresh", {
      method: "POST",
      body: { refresh_token: refreshToken },
      anonymous: true,
    }),

  /**
   * Thu hồi refresh token (và vô hiệu hoá FCM token của thiết bị này nếu có).
   * 403 = token thuộc người khác: không thu hồi được gì, nhưng phiên cục bộ vẫn
   * phải bị xoá nên coi như đã đăng xuất.
   */
  logout: async (refreshToken: string, fcmToken?: string | null): Promise<void> => {
    try {
      await request<null>("/auth/logout", {
        method: "POST",
        body: fcmToken ? { refresh_token: refreshToken, fcm_token: fcmToken } : { refresh_token: refreshToken },
      });
    } catch (error) {
      if (error instanceof ApiError && error.status === 403) return;
      throw error;
    }
  },

  changePassword: (currentPassword: string, newPassword: string, accessToken?: string) =>
    request<null>("/auth/change-password", {
      method: "POST",
      body: { current_password: currentPassword, new_password: newPassword },
      accessToken,
    }),

  registerDeviceToken: (fcmToken: string, deviceName?: string, accessToken?: string) =>
    request<null>("/auth/device-token", {
      method: "POST",
      body: { fcm_token: fcmToken, device_name: deviceName },
      accessToken,
    }),
};

