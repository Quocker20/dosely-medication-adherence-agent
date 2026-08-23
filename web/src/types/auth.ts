// Part of src/types/ — xem index.ts cho ràng buộc sync với backend.
// Slice 1 — Authentication

export type UserRole = "ADMIN" | "DOCTOR" | "PATIENT" | "CAREGIVER";

export interface UserResponse {
  id: string;
  phone: string;
  role: UserRole;
  status: string;
}

export interface AuthTokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
  is_first_login: boolean;
  user: UserResponse;
}
