package com.remindrx.app.data.repository

import com.remindrx.app.data.remote.ApiEnvelope
import com.remindrx.app.data.remote.AuthTokenResponseDto
import com.remindrx.app.data.remote.ChangePasswordRequestDto
import com.remindrx.app.data.remote.DeviceTokenRequestDto
import com.remindrx.app.data.remote.LoginRequestDto
import com.remindrx.app.data.remote.LogoutRequestDto
import com.remindrx.app.data.remote.RefreshTokenRequestDto
import com.remindrx.app.data.remote.RemindRxApiService
import javax.inject.Inject
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.flow.StateFlow
import retrofit2.HttpException

class RemoteAuthRepositoryImpl @Inject constructor(
    private val api: RemindRxApiService,
    private val sessionStore: SessionStore,
) : AuthRepository {

    override val session: StateFlow<AuthSession?> = sessionStore.session

    override suspend fun login(phone: String, pin: String): AuthSession =
        authenticate(phone = phone, pin = pin)

    override suspend fun changePin(accessToken: String, currentPin: String, newPin: String) {
        val phone = requireNotNull(sessionStore.phone) {
            "Phiên đăng nhập không có số điện thoại để cấp lại token."
        }
        api.changePassword(
            authorization = "Bearer $accessToken",
            request = ChangePasswordRequestDto(currentPassword = currentPin, newPassword = newPin),
        ).requireSuccess("đổi mã PIN")

        // The backend revokes every refresh token after a password change. Log
        // in again immediately so the persisted session remains renewable.
        try {
            authenticate(phone = phone, pin = newPin)
        } catch (cancellation: CancellationException) {
            sessionStore.clear()
            throw cancellation
        } catch (error: Exception) {
            sessionStore.clear()
            throw error
        }
    }

    override suspend fun refreshSession(): AuthSession {
        val sessionBeforeRefresh = sessionStore.session.value ?: run {
            sessionStore.clear()
            throw IllegalStateException("Không có refresh token trong phiên đăng nhập.")
        }
        return refreshSession(sessionBeforeRefresh)
    }

    private suspend fun refreshSession(sessionBeforeRefresh: AuthSession): AuthSession {
        return try {
            val body = api.refreshToken(RefreshTokenRequestDto(sessionBeforeRefresh.refreshToken))
                .requireData("làm mới phiên đăng nhập")
            check(sessionBeforeRefresh.patientId == body.user.id) {
                "Refresh token không thuộc phiên bệnh nhân hiện tại."
            }
            body.persistedSession().also { renewed ->
                check(sessionStore.updateIfCurrent(sessionBeforeRefresh, renewed)) {
                    "Phiên đăng nhập đã thay đổi trong lúc làm mới token."
                }
            }
        } catch (cancellation: CancellationException) {
            throw cancellation
        } catch (error: Exception) {
            sessionStore.clearIfCurrent(sessionBeforeRefresh)
            throw error
        }
    }

    override suspend fun logout() {
        var sessionBeingLoggedOut = sessionStore.session.value ?: return
        try {
            try {
                api.logout(LogoutRequestDto(sessionBeingLoggedOut.refreshToken))
                    .requireSuccess("đăng xuất")
            } catch (error: HttpException) {
                if (error.code() != 401) throw error

                // Logout needs both a valid access token and the refresh token
                // being revoked. Refresh explicitly so a retried request never
                // carries the already-rotated token in its body.
                val renewed = refreshSession(sessionBeingLoggedOut)
                sessionBeingLoggedOut = renewed
                api.logout(LogoutRequestDto(renewed.refreshToken)).requireSuccess("đăng xuất")
            }
        } finally {
            sessionStore.clearIfCurrent(sessionBeingLoggedOut)
        }
    }

    override suspend fun registerDeviceToken(fcmToken: String, deviceName: String?) {
        try {
            api.registerDeviceToken(
                DeviceTokenRequestDto(fcmToken = fcmToken, deviceName = deviceName)
            )
        } catch (e: Exception) {
            // Log nhưng không ném exception — gửi token thất bại không được làm hỏng app
            android.util.Log.w("DeviceToken", "Failed to register FCM token: ${e.message}")
        }
    }

    private suspend fun authenticate(phone: String, pin: String): AuthSession {
        val body = api.login(LoginRequestDto(phone = phone, password = pin))
            .requireData("đăng nhập")
        return body.persistedSession().also(sessionStore::update)
    }

    private fun AuthTokenResponseDto.persistedSession(): AuthSession = AuthSession(
        accessToken = accessToken,
        refreshToken = refreshToken,
        patientId = user.id,
        mustChangePassword = mustChangePassword,
        needOnboarding = needOnboarding,
        phone = user.phone,
    )

    private fun ApiEnvelope<*>.requireSuccess(operation: String) {
        check(success) { "Không thể $operation: $message" }
    }

    private fun <T : Any> ApiEnvelope<T>.requireData(operation: String): T {
        requireSuccess(operation)
        return requireNotNull(data) { "Phản hồi $operation không có dữ liệu." }
    }
}
