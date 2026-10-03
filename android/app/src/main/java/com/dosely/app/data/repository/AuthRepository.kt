package com.dosely.app.data.repository

import kotlinx.coroutines.flow.StateFlow

data class AuthSession(
    val accessToken: String,
    val refreshToken: String,
    val patientId: String,
    val mustChangePassword: Boolean,
    val needOnboarding: Boolean,
    val phone: String,
)

interface AuthRepository {
    val session: StateFlow<AuthSession?>

    suspend fun login(phone: String, pin: String): AuthSession
    suspend fun changePin(accessToken: String, currentPin: String, newPin: String)
    suspend fun refreshSession(): AuthSession
    suspend fun logout()
    suspend fun registerDeviceToken(fcmToken: String, deviceName: String? = null)
}
