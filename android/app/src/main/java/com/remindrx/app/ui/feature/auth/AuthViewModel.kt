package com.remindrx.app.ui.feature.auth

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
    val session: AuthSession? = null,
)

@HiltViewModel
class AuthViewModel @Inject constructor(
    private val repository: AuthRepository,
) : ViewModel() {
    private val _state = MutableStateFlow(AuthUiState(session = repository.session.value))
    val state: StateFlow<AuthUiState> = _state.asStateFlow()

    init {
        viewModelScope.launch {
            repository.session.collect { session ->
                _state.update { it.copy(session = session) }
            }
        }
    }

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
                .onSuccess { session ->
                    _state.update { it.copy(isLoading = false, session = session) }
                    onSuccess(session.isFirstLogin)
                }
                .onFailure { error ->
                    _state.update { it.copy(isLoading = false, error = error.loginMessage()) }
                }
        }
    }

    fun changePin(
        currentPin: String,
        newPin: String,
        confirmedPin: String,
        onSuccess: () -> Unit,
    ) {
        if (_state.value.isLoading) return
        if (!currentPin.isSixDigitPin()) {
            _state.update { it.copy(error = "Mã PIN hiện tại phải gồm đúng 6 chữ số.") }
            return
        }
        if (!newPin.isSixDigitPin()) {
            _state.update { it.copy(error = "Mã PIN mới phải gồm đúng 6 chữ số.") }
            return
        }
        if (newPin != confirmedPin) {
            _state.update { it.copy(error = "Hai mã PIN chưa khớp.") }
            return
        }
        if (newPin == currentPin) {
            _state.update { it.copy(error = "Mã PIN mới phải khác mã PIN hiện tại.") }
            return
        }

        val accessToken = _state.value.session?.accessToken
        if (accessToken == null) {
            _state.update { it.copy(error = "Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.") }
            return
        }

        viewModelScope.launch {
            _state.update { it.copy(isLoading = true, error = null) }
            runCatching { repository.changePin(accessToken, currentPin, newPin) }
                .onSuccess {
                    _state.update { it.copy(isLoading = false, session = repository.session.value) }
                    onSuccess()
                }
                .onFailure { error ->
                    _state.update { it.copy(isLoading = false, error = error.changePinMessage()) }
                }
        }
    }

    fun logout() {
        if (_state.value.isLoading) return
        viewModelScope.launch {
            _state.update { it.copy(isLoading = true, error = null) }
            runCatching { repository.logout() }
                .onSuccess { _state.update { it.copy(isLoading = false, session = null) } }
                .onFailure {
                    // Remote revocation is best-effort. The repository always clears
                    // local credentials so a failed network call cannot leave the UI logged in.
                    _state.update { state -> state.copy(isLoading = false, session = null) }
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
            "Không thể đổi mã PIN. Vui lòng kiểm tra lại mã PIN hiện tại."
        } else {
            "Không thể đổi mã PIN lúc này. Vui lòng thử lại."
        }
        else -> "Không kết nối được máy chủ RemindRx."
    }
}
