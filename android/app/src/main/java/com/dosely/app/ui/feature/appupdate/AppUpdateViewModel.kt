package com.dosely.app.ui.feature.appupdate

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.dosely.app.BuildConfig
import com.dosely.app.data.AppUpdateInfo
import com.dosely.app.data.repository.AppUpdateRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import javax.inject.Inject
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.CancellationException

data class AppUpdateUiState(
    val availableUpdate: AppUpdateInfo? = null,
)

@HiltViewModel
class AppUpdateViewModel @Inject constructor(
    private val repository: AppUpdateRepository,
) : ViewModel() {
    private val _state = MutableStateFlow(AppUpdateUiState())
    val state: StateFlow<AppUpdateUiState> = _state.asStateFlow()

    private var hasCheckedThisSession = false

    init {
        checkForUpdate()
    }

    /** Network and malformed-response failures must never block app startup. */
    fun checkForUpdate() {
        if (hasCheckedThisSession) return
        hasCheckedThisSession = true

        viewModelScope.launch {
            val latest = try {
                repository.getLatestVersion()
            } catch (error: Exception) {
                if (error is CancellationException) throw error
                return@launch
            }
            if (latest.versionCode > BuildConfig.VERSION_CODE) {
                _state.value = AppUpdateUiState(availableUpdate = latest)
            }
        }
    }

    fun dismissUpdate() {
        _state.value = AppUpdateUiState()
    }
}
