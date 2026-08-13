package com.remindrx.app.ui

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.remindrx.app.data.DoseToday
import com.remindrx.app.data.MockRepository
import com.remindrx.app.data.RoutineItem
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
    val isSavingRoutine: Boolean = false,
    val routineError: String? = null,
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
                            error = error.toVietnameseUiMessage(
                                "Không thể tải dữ liệu RemindRx lúc này.",
                            ),
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
                            error = error.toVietnameseUiMessage("Không ghi nhận được cữ thuốc."),
                        )
                    }
                }
        }
    }

    fun saveRoutine(routine: List<RoutineItem>) {
        if (_state.value.isSavingRoutine) return
        if (routine.size != 5 || routine.any { !it.time.isValidTime() }) {
            _state.update { it.copy(routineError = "Vui lòng nhập giờ hợp lệ theo định dạng HH:mm.") }
            return
        }

        viewModelScope.launch {
            _state.update { it.copy(isSavingRoutine = true, routineError = null) }
            runCatching { repository.updateRoutine(routine) }
                .onSuccess { updated ->
                    _state.update {
                        it.copy(
                            routine = updated,
                            isSavingRoutine = false,
                            routineError = null,
                            message = "Đã lưu thói quen sinh hoạt",
                        )
                    }
                }
                .onFailure { error ->
                    _state.update {
                        it.copy(
                            isSavingRoutine = false,
                            routineError = error.toVietnameseUiMessage(
                                "Không lưu được thói quen sinh hoạt.",
                            ),
                        )
                    }
                }
        }
    }

    fun clearRoutineError() {
        _state.update { it.copy(routineError = null) }
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
                _state.update {
                    it.copy(error = error.toVietnameseUiMessage("Không gửi được khảo sát."))
                }
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
                _state.update {
                    it.copy(
                        error = error.toVietnameseUiMessage(
                            "Không gửi được SOS. Hãy gọi cấp cứu ngay.",
                        ),
                    )
                }
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

    private fun String.isValidTime(): Boolean {
        val parts = split(':')
        if (parts.size != 2 || parts.any { it.length != 2 || !it.all(Char::isDigit) }) return false
        val hour = parts[0].toInt()
        val minute = parts[1].toInt()
        return hour in 0..23 && minute in 0..59
    }
}
