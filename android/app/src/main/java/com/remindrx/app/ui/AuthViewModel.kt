package com.remindrx.app.ui

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.remindrx.app.data.repository.AuthRepository
import com.remindrx.app.data.repository.AuthSession
import dagger.hilt.android.lifecycle.HiltViewModel
import javax.inject.Inject
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import retrofit2.HttpException

data class AuthUiState(
    val isLoading: Boolean = false,
    val error: String? = null,
)

@HiltViewModel
class AuthViewModel @Inject constructor(
    private val repository: AuthRepository,
) : ViewModel() {
    private val _state = MutableStateFlow(AuthUiState())
    val state: StateFlow<AuthUiState> = _state.asStateFlow()

    private var session: AuthSession? = null
    private var loginPin: String? = null

    fun login(phone: String, pin: String, onSuccess: (isFirstLogin: Boolean) -> Unit) {
        if (_state.value.isLoading) return
        if (phone.isBlank()) {
            _state.update { it.copy(error = "Vui lòng nhập số điện thoại.") }
            return
        }
        if (!pin.isSixDigitPin()) {
            _state.update { it.copy(error = "Mã PIN phải gồm đúng 6 chữ số.") }
            return
        }

        viewModelScope.launch {
            _state.update { it.copy(isLoading = true, error = null) }
            runCatching { repository.login(phone, pin) }
                .onSuccess { authenticatedSession ->
                    session = authenticatedSession
                    loginPin = pin
                    _state.update { it.copy(isLoading = false) }
                    onSuccess(authenticatedSession.isFirstLogin)
                }
                .onFailure { error ->
                    _state.update {
                        it.copy(isLoading = false, error = error.loginMessage())
                    }
                }
        }
    }

    fun changePin(newPin: String, confirmedPin: String, onSuccess: () -> Unit) {
        if (_state.value.isLoading) return
        if (!newPin.isSixDigitPin()) {
            _state.update { it.copy(error = "Mã PIN mới phải gồm đúng 6 chữ số.") }
            return
        }
        if (newPin != confirmedPin) {
            _state.update { it.copy(error = "Hai mã PIN chưa khớp.") }
            return
        }

        val authenticatedSession = session
        val currentPin = loginPin
        if (authenticatedSession == null || currentPin == null) {
            _state.update { it.copy(error = "Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.") }
            return
        }
        if (newPin == currentPin) {
            _state.update { it.copy(error = "Mã PIN mới phải khác mã PIN ban đầu.") }
            return
        }

        viewModelScope.launch {
            _state.update { it.copy(isLoading = true, error = null) }
            runCatching {
                repository.changePin(
                    accessToken = authenticatedSession.accessToken,
                    currentPin = currentPin,
                    newPin = newPin,
                )
            }.onSuccess {
                loginPin = newPin
                session = authenticatedSession.copy(isFirstLogin = false)
                _state.update { it.copy(isLoading = false) }
                onSuccess()
            }.onFailure { error ->
                _state.update {
                    it.copy(isLoading = false, error = error.changePinMessage())
                }
            }
        }
    }

    fun clearError() {
        _state.update { it.copy(error = null) }
    }

    private fun String.isSixDigitPin(): Boolean = length == 6 && all(Char::isDigit)

    private fun Throwable.loginMessage(): String = when (this) {
        is HttpException -> if (code() == 401) {
            "Số điện thoại hoặc mã PIN không đúng."
        } else {
            "Không thể đăng nhập lúc này. Vui lòng thử lại."
        }
        else -> "Không kết nối được máy chủ RemindRx."
    }

    private fun Throwable.changePinMessage(): String = when (this) {
        is HttpException -> if (code() in 400..499) {
            "Không thể đổi mã PIN. Vui lòng kiểm tra lại mã PIN."
        } else {
            "Không thể đổi mã PIN lúc này. Vui lòng thử lại."
        }
        else -> "Không kết nối được máy chủ RemindRx."
    }
}
