package com.dosely.app.data.remote

// Khớp src/modules/auth/schemas.py

data class LoginRequestDto(val phone: String, val password: String)

data class ChangePasswordRequestDto(val currentPassword: String, val newPassword: String)

data class RefreshTokenRequestDto(val refreshToken: String)

data class LogoutRequestDto(val refreshToken: String)

data class UserDto(val id: String, val phone: String, val role: String, val status: String)

data class AuthTokenResponseDto(
    val accessToken: String,
    val refreshToken: String,
    val tokenType: String,
    val expiresIn: Int,
    val mustChangePassword: Boolean,
    val needOnboarding: Boolean,
    val user: UserDto,
)

// Khớp src/modules/auth/schemas.py DeviceTokenRequest
data class DeviceTokenRequestDto(
    val fcmToken: String,
    val deviceName: String? = null,
)
