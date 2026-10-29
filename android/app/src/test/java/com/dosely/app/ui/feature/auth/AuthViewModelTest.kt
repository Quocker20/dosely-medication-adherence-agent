package com.dosely.app.ui.feature.auth

import com.dosely.app.data.repository.AuthRepository
import com.dosely.app.data.repository.AuthSession
import com.dosely.app.testing.MainDispatcherRule
import java.io.IOException
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.advanceTimeBy
import kotlinx.coroutines.test.runTest
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.ResponseBody.Companion.toResponseBody
import retrofit2.HttpException
import retrofit2.Response
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Assert.assertNull
import org.junit.Assert.assertSame
import org.junit.Rule
import org.junit.Test

@OptIn(ExperimentalCoroutinesApi::class)
class AuthViewModelTest {
    @get:Rule
    val mainDispatcherRule = MainDispatcherRule()

    @Test
    fun `session expiry emitted by repository clears authenticated UI state`() {
        val repository = FakeAuthRepository(authSession())
        val viewModel = AuthViewModel(repository)
        assertSame(repository.session.value, viewModel.state.value.session)

        repository.expireSession()

        assertNull(viewModel.state.value.session)
    }

    @Test
    fun `lockout 429 shows the server message and counts down before login is allowed again`() = runTest {
        val lock = "Bạn đã nhập sai quá nhiều lần. Vui lòng thử lại sau 1 phút."
        val repository = FakeAuthRepository(null).apply {
            loginFailure = tooManyRequests(lock, 3)
        }
        val viewModel = AuthViewModel(repository)

        viewModel.login("0901234567", "123456") {}
        advanceTimeBy(500)

        assertEquals(lock, viewModel.state.value.error)
        assertEquals(3, viewModel.state.value.lockRemainingSeconds)
        assertEquals(1, repository.loginCalls)

        // Locked: another attempt must not hit the server.
        viewModel.login("0901234567", "123456") {}
        assertEquals(1, repository.loginCalls)

        advanceTimeBy(1_001)
        assertEquals(2, viewModel.state.value.lockRemainingSeconds)
        advanceTimeBy(2_000)
        assertEquals(0, viewModel.state.value.lockRemainingSeconds)

        viewModel.login("0901234567", "123456") {}
        advanceTimeBy(500)
        assertEquals(2, repository.loginCalls)
    }

    @Test
    fun `per-IP 429 uses own Vietnamese text and also locks the form`() = runTest {
        val repository = FakeAuthRepository(null).apply {
            loginFailure = tooManyRequests("Quá 10 yêu cầu / 60s cho login.", 20)
        }
        val viewModel = AuthViewModel(repository)

        viewModel.login("0901234567", "123456") {}
        advanceTimeBy(500)

        assertTrue(viewModel.state.value.error!!.startsWith("Bạn thao tác quá nhanh"))
        assertEquals(20, viewModel.state.value.lockRemainingSeconds)
    }

    @Test
    fun `logout clears UI session even when remote revocation fails`() {
        val failure = IOException("backend unavailable")
        val repository = FakeAuthRepository(authSession()).apply {
            logoutFailure = failure
        }
        val viewModel = AuthViewModel(repository)

        viewModel.logout()

        assertEquals(1, repository.logoutCalls)
        assertNull(repository.session.value)
        assertNull(viewModel.state.value.session)
        assertFalse(viewModel.state.value.isLoading)
    }
}

private class FakeAuthRepository(initialSession: AuthSession?) : AuthRepository {
    private val mutableSession = MutableStateFlow(initialSession)
    override val session: StateFlow<AuthSession?> = mutableSession.asStateFlow()
    var logoutCalls: Int = 0
    var logoutFailure: Throwable? = null
    var loginFailure: Throwable? = null
    var loginCalls: Int = 0

    fun expireSession() {
        mutableSession.value = null
    }

    override suspend fun logout() {
        logoutCalls += 1
        mutableSession.value = null
        logoutFailure?.let { throw it }
    }

    override suspend fun login(phone: String, pin: String): AuthSession {
        loginCalls += 1
        loginFailure?.let { throw it }
        return authSession()
    }

    override suspend fun changePin(accessToken: String, currentPin: String, newPin: String) {
        error("Not used")
    }

    override suspend fun refreshSession(): AuthSession = error("Not used")

    override suspend fun registerDeviceToken(fcmToken: String, deviceName: String?) {
        // No-op: FCM sync is best-effort and irrelevant to these auth-flow tests.
    }
}

private fun authSession(): AuthSession = AuthSession(
    accessToken = "access-token",
    refreshToken = "refresh-token",
    patientId = "patient-1",
    mustChangePassword = false,
    needOnboarding = false,
    phone = "+84901234567",
)

private fun tooManyRequests(message: String, retryAfter: Int): HttpException = HttpException(
    Response.error<Any>(
        429,
        """{"success":false,"code":429,"message":"$message","data":null,"errors":{"retry_after_seconds":$retryAfter}}"""
            .toResponseBody("application/json".toMediaType()),
    ),
)
