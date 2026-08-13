package com.remindrx.app.data.repository

import com.remindrx.app.data.remote.ChangePasswordRequestDto
import com.remindrx.app.data.remote.LoginRequestDto
import com.remindrx.app.data.remote.RemindRxApiService
import javax.inject.Inject

class RemoteAuthRepositoryImpl @Inject constructor(
    private val api: RemindRxApiService,
    private val sessionStore: SessionStore,
) : AuthRepository {

    override suspend fun login(phone: String, pin: String): AuthSession {
        val body = requireNotNull(api.login(LoginRequestDto(phone = phone, password = pin)).data) {
            "Phản hồi đăng nhập rỗng"
        }
        sessionStore.update(accessToken = body.accessToken, patientId = body.user.id)
        return AuthSession(
            accessToken = body.accessToken,
            patientId = body.user.id,
            isFirstLogin = body.isFirstLogin,
        )
    }

    override suspend fun changePin(accessToken: String, currentPin: String, newPin: String) {
        api.changePassword(
            authorization = "Bearer $accessToken",
            request = ChangePasswordRequestDto(currentPassword = currentPin, newPassword = newPin),
        )
    }
}
