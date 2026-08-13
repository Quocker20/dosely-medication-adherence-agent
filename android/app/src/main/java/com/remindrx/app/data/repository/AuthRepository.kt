package com.remindrx.app.data.repository

data class AuthSession(val accessToken: String, val patientId: String, val isFirstLogin: Boolean)

interface AuthRepository {
    suspend fun login(phone: String, pin: String): AuthSession
    suspend fun changePin(accessToken: String, currentPin: String, newPin: String)
}
