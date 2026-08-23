import uuid
from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    """Request schema for PIN password login."""

    phone: str
    password: str


class ChangePasswordRequest(BaseModel):
    """Request schema for first-time or explicit PIN password change."""

    current_password: str = Field(..., min_length=6, max_length=6, pattern=r"^\d{6}$")
    new_password: str = Field(..., min_length=6, max_length=6, pattern=r"^\d{6}$")


class UserResponse(BaseModel):
    """DTO representing basic user details."""

    id: uuid.UUID
    phone: str
    role: str
    status: str


class AuthTokenResponse(BaseModel):
    """Response schema returning authentication tokens."""

    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    expires_in: int
    is_first_login: bool
    user: UserResponse


class RefreshTokenRequest(BaseModel):
    """Request schema to refresh JWT access token."""

    refresh_token: str


class LogoutRequest(BaseModel):
    """Request schema to logout/revoke session."""

    refresh_token: str


class MessageResponse(BaseModel):
    """Simple message response schema."""

    message: str


class DeviceTokenRequest(BaseModel):
    """Request schema for registering/updating FCM device token."""

    fcm_token: str = Field(..., max_length=255)
    device_name: str | None = Field(None, max_length=100)
