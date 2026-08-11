package com.remindrx.app.ui

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.remindrx.app.data.DoseToday
import com.remindrx.app.data.MockRepository
import com.remindrx.app.data.repository.PatientHome
import com.remindrx.app.data.repository.PatientRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import javax.inject.Inject
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

data class PatientUiState(
    val isLoading: Boolean = true,
    val error: String? = null,
    val routine: List<com.remindrx.app.data.RoutineItem> = MockRepository.routine,
    val doses: List<DoseToday> = MockRepository.todayDoses,
    val medications: List<com.remindrx.app.data.Medication> = MockRepository.medications,
    val adherenceRate: Int = 0,
    val busyDoseIds: Set<String> = emptySet(),
    val message: String? = null,
)

@HiltViewModel
class PatientViewModel @Inject constructor(
    private val repository: PatientRepository,
) : ViewModel() {
    private val _state = MutableStateFlow(PatientUiState())
    val state: StateFlow<PatientUiState> = _state.asStateFlow()

    init {
        refresh()
    }

    fun refresh() {
        viewModelScope.launch {
            _state.update { it.copy(isLoading = true, error = null) }
            runCatching { repository.loadHome() }
                .onSuccess(::showHome)
                .onFailure { error ->
                    _state.update {
                        it.copy(
                            isLoading = false,
                            error = error.message ?: "Không kết nối được máy chủ RemindRx.",
                        )
                    }
                }
        }
    }

    fun recordDoseAction(doseId: String, action: String, note: String = "") {
        if (doseId in _state.value.busyDoseIds) return
        viewModelScope.launch {
            _state.update { it.copy(busyDoseIds = it.busyDoseIds + doseId, error = null) }
            runCatching { repository.recordDoseAction(doseId, action, note) }
                .onSuccess {
                    val home = repository.loadHome()
                    showHome(home, "Đã ghi nhận cữ thuốc")
                }
                .onFailure { error ->
                    _state.update {
                        it.copy(
                            busyDoseIds = it.busyDoseIds - doseId,
                            error = error.message ?: "Không ghi nhận được cữ thuốc.",
                        )
                    }
                }
        }
    }

    fun submitSurvey(mood: Int, symptom: String, severity: String) {
        viewModelScope.launch {
            runCatching {
                repository.submitHealthSurvey(
                    mood = mood,
                    symptoms = if (symptom == "Không có") emptyList() else listOf(symptom),
                    severity = severity,
                )
            }.onSuccess {
                _state.update {
                    it.copy(message = if (severity == "SEVERE") "Đã gửi cảnh báo cho bác sĩ" else "Đã gửi khảo sát")
                }
            }.onFailure { error ->
                _state.update { it.copy(error = error.message ?: "Không gửi được khảo sát.") }
            }
        }
    }

    fun createSos() {
        viewModelScope.launch {
            runCatching {
                repository.createSos(note = "SOS từ ứng dụng bệnh nhân", shareLocation = false)
            }.onSuccess {
                _state.update { it.copy(message = "Red Alert đã gửi tới bác sĩ và người thân") }
            }.onFailure { error ->
                _state.update { it.copy(error = error.message ?: "Không gửi được SOS. Hãy gọi cấp cứu ngay.") }
            }
        }
    }

    fun clearMessage() {
        _state.update { it.copy(message = null) }
    }

    private fun showHome(home: PatientHome, message: String? = _state.value.message) {
        _state.update {
            it.copy(
                isLoading = false,
                error = null,
                routine = home.routine,
                doses = home.doses,
                medications = home.medications,
                adherenceRate = home.adherenceRate,
                busyDoseIds = emptySet(),
                message = message,
            )
        }
    }
}
