package com.dosely.app.ui.feature.auth

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.dosely.app.data.repository.AuthRepository
import com.dosely.app.data.repository.AuthSession
import com.dosely.app.ui.toVietnameseUiMessage
import com.dosely.app.ui.validateVnPhone
import dagger.hilt.android.lifecycle.HiltViewModel
import javax.inject.Inject
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import retrofit2.HttpException

data class AuthUiState(
    val isLoading: Boolean = false,
    val error: String? = null,
    val session: AuthSession? = null,
    val shouldClearLoginPin: Boolean = false,
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

    fun login(phone: String, pin: String, onSuccess: (mustChangePassword: Boolean) -> Unit) {
        if (_state.value.isLoading) return
        if (!validateVnPhone(phone).ok) {
            _state.update { it.copy(error = "Số điện thoại không đúng định dạng (VD: 0901234567)") }
            return
        }
        if (!pin.isSixDigitPin()) {
            _state.update { it.copy(error = "Mã PIN phải gồm đúng 6 chữ số.") }
            return
        }

        viewModelScope.launch {
            _state.update { it.copy(isLoading = true, error = null) }
            val startedAt = System.currentTimeMillis()
            val result = runCatching { repository.login(phone, pin) }
            val remainingDelay = MIN_LOGIN_DELAY_MS - (System.currentTimeMillis() - startedAt)
            if (remainingDelay > 0) delay(remainingDelay)
            result
                .onSuccess { session ->
                    _state.update { it.copy(isLoading = false, session = session) }
                    // B2: Đồng bộ FCM token vào user_devices ngay sau khi login
                    syncFcmTokenAfterLogin()
                    onSuccess(session.mustChangePassword)
                }
                .onFailure { error ->
                    _state.update {
                        it.copy(
                            isLoading = false,
                            error = error.loginMessage(),
                            shouldClearLoginPin = error is HttpException && error.code() == 401,
                        )
                    }
                }
        }
    }

    private fun syncFcmTokenAfterLogin() {
        viewModelScope.launch {
            try {
                com.google.firebase.messaging.FirebaseMessaging.getInstance().token
                    .addOnSuccessListener { token ->
                        viewModelScope.launch {
                            repository.registerDeviceToken(
                                fcmToken = token,
                                deviceName = android.os.Build.MODEL,
                            )
                        }
                    }
            } catch (e: Exception) {
                android.util.Log.w("FCM_TOKEN", "Không thể đồng bộ FCM token sau login: ${e.message}")
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
        _state.update { it.copy(error = null, shouldClearLoginPin = false) }
    }

    fun consumeClearLoginPin() {
        _state.update { it.copy(shouldClearLoginPin = false) }
    }

    private fun String.isSixDigitPin(): Boolean = length == 6 && all(Char::isDigit)

    private fun Throwable.loginMessage(): String = when (this) {
        is HttpException -> if (code() == 401) {
            "Số điện thoại hoặc mã PIN không đúng."
        } else {
            "Không thể đăng nhập lúc này. Vui lòng thử lại."
        }
        else -> toVietnameseUiMessage(fallback = "Không đăng nhập được, vui lòng thử lại.")
    }

    private fun Throwable.changePinMessage(): String = when (this) {
        is HttpException -> if (code() in 400..499) {
            "Không thể đổi mã PIN. Vui lòng kiểm tra lại mã PIN hiện tại."
        } else {
            "Không thể đổi mã PIN lúc này. Vui lòng thử lại."
        }
        else -> "Không kết nối được máy chủ Dosely."
    }
}

private const val MIN_LOGIN_DELAY_MS = 400L
