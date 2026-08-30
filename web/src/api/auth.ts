// Slice 1: Authentication
import { request } from "./client";
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

  logout: (refreshToken: string) =>
    request<null>("/auth/logout", { method: "POST", body: { refresh_token: refreshToken } }),

  changePassword: (currentPassword: string, newPassword: string, accessToken?: string) =>
    request<null>("/auth/change-password", {
      method: "POST",
      body: { current_password: currentPassword, new_password: newPassword },
      accessToken,
    }),
};
