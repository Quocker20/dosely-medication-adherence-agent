package com.remindrx.app.ui.feature.auth

import com.remindrx.app.data.repository.AuthRepository
import com.remindrx.app.data.repository.AuthSession
import com.remindrx.app.testing.MainDispatcherRule
import java.io.IOException
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertSame
import org.junit.Rule
import org.junit.Test

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

    fun expireSession() {
        mutableSession.value = null
    }

    override suspend fun logout() {
        logoutCalls += 1
        mutableSession.value = null
        logoutFailure?.let { throw it }
    }

    override suspend fun login(phone: String, pin: String): AuthSession = error("Not used")

    override suspend fun changePin(accessToken: String, currentPin: String, newPin: String) {
        error("Not used")
    }

    override suspend fun refreshSession(): AuthSession = error("Not used")
}

private fun authSession(): AuthSession = AuthSession(
    accessToken = "access-token",
    refreshToken = "refresh-token",
    patientId = "patient-1",
    isFirstLogin = false,
    phone = "+84901234567",
)
