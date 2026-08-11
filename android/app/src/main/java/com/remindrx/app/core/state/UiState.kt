package com.remindrx.app.core.state

/** Wrapper chung cho state của ViewModel — dùng khi màn hình chuyển từ mock sang gọi backend thật. */
sealed interface UiState<out T> {
    data object Loading : UiState<Nothing>
    data class Success<T>(val data: T) : UiState<T>
    data class Error(val message: String) : UiState<Nothing>
}
