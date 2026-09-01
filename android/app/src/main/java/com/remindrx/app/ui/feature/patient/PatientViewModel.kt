package com.remindrx.app.ui.feature.patient

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.remindrx.app.core.connectivity.AlwaysOnlineConnectivityObserver
import com.remindrx.app.core.connectivity.ConnectivityObserver
import com.remindrx.app.data.AdherenceLog
import com.remindrx.app.data.AdherenceSummary
import com.remindrx.app.data.CaregiverLink
import com.remindrx.app.data.DoseAction
import com.remindrx.app.data.DoseStatus
import com.remindrx.app.data.DoseToday
import com.remindrx.app.data.Medication
import com.remindrx.app.data.MedicationDetail
import com.remindrx.app.data.RoutineItem
import com.remindrx.app.data.ScheduleUpdateStatus
import com.remindrx.app.data.SurveySeverity
import com.remindrx.app.data.SurveySymptom
import com.remindrx.app.data.SymptomCode
import com.remindrx.app.data.repository.PatientHome
import com.remindrx.app.data.repository.PatientRepository
import com.remindrx.app.data.repository.NoOpOutboxSyncScheduler
import com.remindrx.app.data.repository.OutboxSyncScheduler
import com.remindrx.app.core.PatientRealtimeEventType
import com.remindrx.app.core.PatientRealtimeEvents
import com.remindrx.app.core.NoopPatientRealtimeEvents
import com.remindrx.app.ui.toVietnameseUiMessage
import dagger.hilt.android.lifecycle.HiltViewModel
import java.time.DayOfWeek
import java.time.Instant
import java.time.LocalDate
import java.time.OffsetDateTime
import java.time.Duration
import java.time.temporal.TemporalAdjusters
import java.util.Collections
import javax.inject.Inject
import kotlinx.coroutines.CoroutineStart
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.collect
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import retrofit2.HttpException

private fun defaultRoutine(): List<RoutineItem> = listOf(
    RoutineItem("wake_time", "Thức dậy", "06:30"),
    RoutineItem("breakfast_time", "Ăn sáng", "07:00"),
    RoutineItem("lunch_time", "Ăn trưa", "11:30"),
    RoutineItem("dinner_time", "Ăn tối", "18:00"),
    RoutineItem("sleep_time", "Đi ngủ", "22:00"),
)

private fun currentWeekStart(today: LocalDate = LocalDate.now()): LocalDate =
    today.with(TemporalAdjusters.previousOrSame(DayOfWeek.MONDAY))

enum class SosSubmissionStatus { IDLE, SENDING, SENT, QUEUED_OFFLINE, FAILED }

private const val DOSE_LOCK_RESCAN_INTERVAL_MS = 30_000L
private val DOSE_LOCK_EARLY_UNLOCK_WINDOW: Duration = Duration.ofMinutes(15)

data class CreatedCaregiverInvite(
    val linkCode: String,
    val telegramDeepLink: String?,
)

data class PatientUiState(
    val isCheckingRoutine: Boolean = false,
    val routineCheckCompleted: Boolean = false,
    val isLoading: Boolean = false,
    val error: String? = null,
    val routine: List<RoutineItem> = defaultRoutine(),
    val doses: List<DoseToday> = emptyList(),
    val medications: List<Medication> = emptyList(),
    val adherence: AdherenceSummary? = null,
    val adherenceRate: Int = 0,
    val busyDoseIds: Set<String> = emptySet(),
    val isSavingRoutine: Boolean = false,
    val routineSaveCompleted: Boolean = false,
    val routineError: String? = null,
    val message: String? = null,
    val isSubmittingSurvey: Boolean = false,
    val isSurveySubmitted: Boolean = false,
    val surveyError: String? = null,
    val sosStatus: SosSubmissionStatus = SosSubmissionStatus.IDLE,
    val sosError: String? = null,
    val medicationDetail: MedicationDetail? = null,
    val medicationDetailId: String? = null,
    val isLoadingMedicationDetail: Boolean = false,
    val medicationDetailError: String? = null,
    val caregivers: List<CaregiverLink> = emptyList(),
    val isLoadingCaregivers: Boolean = false,
    val isAddingCaregiver: Boolean = false,
    val deletingCaregiverId: String? = null,
    val caregiverError: String? = null,
    val createdCaregiverTemporaryPin: String? = null,
    val createdCaregiverInvite: CreatedCaregiverInvite? = null,
    val historyWeekStart: LocalDate = currentWeekStart(),
    val historySummary: AdherenceSummary? = null,
    val historyLogs: List<AdherenceLog> = emptyList(),
    val historyPage: Int = 1,
    val historyHasMore: Boolean = false,
    val isLoadingHistory: Boolean = false,
    val isLoadingMoreHistory: Boolean = false,
    val historyError: String? = null,
    val pendingSyncCount: Int = 0,
)

@HiltViewModel
class PatientViewModel @Inject constructor(
    private val repository: PatientRepository,
    private val realtimeSync: PatientRealtimeEvents,
    private val connectivityObserver: ConnectivityObserver,
    private val outboxSyncScheduler: OutboxSyncScheduler,
) : ViewModel() {
    constructor(repository: PatientRepository) : this(
        repository,
        NoopPatientRealtimeEvents,
        AlwaysOnlineConnectivityObserver,
        NoOpOutboxSyncScheduler(),
    )
    private val _state = MutableStateFlow(PatientUiState())
    val state: StateFlow<PatientUiState> = _state.asStateFlow()
    val isOnline: StateFlow<Boolean> = connectivityObserver.isOnline
    private var activePatientId: String? = null
    private var sessionRevision: Long = 0
    private val sessionJobs = Collections.synchronizedSet(mutableSetOf<Job>())
    private var pendingSyncJob: Job? = null

    init {
        viewModelScope.launch {
            realtimeSync.events.collect { event ->
                when (event.type) {
                    PatientRealtimeEventType.ROUTINE_UPDATED -> reloadRoutineFromServer()
                    PatientRealtimeEventType.SCHEDULE_UPDATED -> refresh()
                }
            }
        }
        monitorConnectivityRestored()
        watchDoseLockExpiry()
    }

    /**
     * DoseToday.status is frozen at fetch/mapping time (Instant.now() read once
     * in PatientMappers.toDoseToday()), so a LOCKED dose never flips to
     * UPCOMING on its own once its scheduled time passes — Compose has nothing
     * to observe for the wall clock ticking forward. Re-scan client-side every
     * 30s so the dashboard doesn't need a manual reload to show a dose as
     * actionable right when its time arrives.
     */
    private fun watchDoseLockExpiry() {
        viewModelScope.launch {
            while (true) {
                delay(DOSE_LOCK_RESCAN_INTERVAL_MS)
                unlockDueDoses()
            }
        }
    }

    private fun unlockDueDoses() {
        val now = Instant.now()
        _state.update { current ->
            var changed = false
            val doses = current.doses.map { dose ->
                if (dose.status == DoseStatus.LOCKED && dose.isNowDue(now)) {
                    changed = true
                    dose.copy(status = DoseStatus.UPCOMING)
                } else {
                    dose
                }
            }
            if (changed) current.copy(doses = doses) else current
        }
    }

    private fun DoseToday.isNowDue(now: Instant): Boolean {
        val scheduledAt = currentScheduledAt ?: return false
        val dueInstant = runCatching { OffsetDateTime.parse(scheduledAt).toInstant() }.getOrNull() ?: return false
        // Unlock a bit ahead of the exact minute so the patient can act as soon
        // as they open the app around dose time, not only after it strikes.
        return !dueInstant.minus(DOSE_LOCK_EARLY_UNLOCK_WINDOW).isAfter(now)
    }

    /** Called by the authenticated navigation shell; never fetch before login. */
    fun startSession(patientId: String) {
        if (activePatientId == patientId) return
        invalidateSession()
        activePatientId = patientId
        _state.value = PatientUiState(isCheckingRoutine = true)
        startPendingSyncCountCollection()
        checkRoutineOnboarding()
    }

    fun endSession() {
        invalidateSession()
        activePatientId = null
        _state.value = PatientUiState()
    }

    fun retrySessionBootstrap() {
        if (activePatientId == null || _state.value.isCheckingRoutine) return
        _state.update { it.copy(isCheckingRoutine = true, error = null) }
        checkRoutineOnboarding()
    }

    private fun checkRoutineOnboarding() {
        launchInSession { revision ->
            runCatching { repository.getRoutine() }
                .onSuccess { routine ->
                    val editableRoutine = defaultRoutine().map { default ->
                        routine.firstOrNull { it.key == default.key }
                            ?.takeIf { it.time.isValidTime() }
                            ?: default
                    }
                    updateForSession(revision) {
                        it.copy(
                            routine = editableRoutine,
                            isCheckingRoutine = false,
                            routineCheckCompleted = true,
                            error = null,
                        )
                    }
                    if (isCurrentSession(revision)) refresh()
                }
                .onFailure { error ->
                    updateForSession(revision) {
                        if (error is HttpException && error.code() == 404) {
                            it.copy(
                                isCheckingRoutine = false,
                                routineCheckCompleted = true,
                                error = null,
                            )
                        } else {
                            it.copy(
                                isCheckingRoutine = false,
                                routineCheckCompleted = false,
                                error = error.toVietnameseUiMessage(
                                    "Không kiểm tra được thói quen sinh hoạt.",
                                ),
                            )
                        }
                    }
                }
        }
    }

    fun refresh() {
        if (activePatientId == null) return
        launchInSession { revision ->
            updateForSession(revision) { it.copy(isLoading = true, error = null) }
            runCatching { repository.loadHome() }
                .onSuccess { home -> showHome(home, revision = revision) }
                .onFailure { error ->
                    updateForSession(revision) {
                        it.copy(
                            isLoading = false,
                            error = error.toVietnameseUiMessage("Không thể tải dữ liệu RemindRx lúc này."),
                        )
                    }
                }
        }
    }

    /** Reload after a minimal realtime event; never merge client-held times. */
    private fun reloadRoutineFromServer() {
        if (activePatientId == null) return
        launchInSession { revision ->
            runCatching { repository.getRoutine() }
                .onSuccess { routine ->
                    val editableRoutine = defaultRoutine().map { default ->
                        routine.firstOrNull { it.key == default.key }
                            ?.takeIf { it.time.isValidTime() }
                            ?: default
                    }
                    updateForSession(revision) { it.copy(routine = editableRoutine) }
                }
        }
    }

    fun recordDoseAction(doseId: String, action: String, note: String = "") {
        if (doseId in _state.value.busyDoseIds) return
        val doseAction = runCatching { DoseAction.valueOf(action) }.getOrNull()
        if (doseAction == null) {
            _state.update { it.copy(error = "Thao tác cữ thuốc không hợp lệ.") }
            return
        }
        launchInSession { revision ->
            updateForSession(revision) {
                it.copy(busyDoseIds = it.busyDoseIds + doseId, error = null)
            }
            runCatching { repository.recordDoseAction(doseId, doseAction, note.ifBlank { null }) }
                .onSuccess {
                    runCatching { repository.loadHome() }
                        .onSuccess { home ->
                            showHome(home, "Đã ghi nhận cữ thuốc", revision)
                        }
                        .onFailure { refreshError ->
                            updateForSession(revision) {
                                it.copy(
                                    busyDoseIds = it.busyDoseIds - doseId,
                                    error = refreshError.toVietnameseUiMessage(
                                        "Đã ghi nhận cữ thuốc nhưng chưa tải lại được lịch.",
                                    ),
                                )
                            }
                        }
                }
                .onFailure { error ->
                    updateForSession(revision) {
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

        launchInSession { revision ->
            updateForSession(revision) {
                it.copy(isSavingRoutine = true, routineSaveCompleted = false, routineError = null)
            }
            runCatching { repository.updateRoutine(routine) }
                .onSuccess { result ->
                    val statusMessage = when (result.scheduleStatus) {
                        ScheduleUpdateStatus.UPDATED -> "Đã lưu thói quen và cập nhật lịch uống thuốc"
                        ScheduleUpdateStatus.TIMED_OUT -> "Đã lưu thói quen; lịch thuốc vẫn đang được cập nhật"
                        ScheduleUpdateStatus.FAILED -> "Đã lưu thói quen nhưng chưa cập nhật được lịch thuốc"
                        ScheduleUpdateStatus.QUEUED_OFFLINE ->
                            "Đã lưu thói quen trên máy, chờ đồng bộ khi có mạng"
                    }
                    updateForSession(revision) {
                        it.copy(
                            routine = result.routine,
                            isSavingRoutine = false,
                            routineSaveCompleted = true,
                            routineError = result.errorMessage.takeIf {
                                result.scheduleStatus == ScheduleUpdateStatus.FAILED
                            },
                            message = statusMessage,
                        )
                    }
                    if (isCurrentSession(revision)) refresh()
                }
                .onFailure { error ->
                    updateForSession(revision) {
                        it.copy(
                            isSavingRoutine = false,
                            routineError = error.toVietnameseUiMessage("Không lưu được thói quen sinh hoạt."),
                        )
                    }
                }
        }
    }

    fun clearRoutineError() {
        _state.update { it.copy(routineError = null) }
    }

    fun consumeRoutineSaveCompleted() {
        _state.update { it.copy(routineSaveCompleted = false) }
    }

    fun submitSurvey(mood: Int, symptomCode: String, severity: String, customDescription: String? = null) {
        if (_state.value.isSubmittingSurvey) return
        val parsedSeverity = runCatching { SurveySeverity.valueOf(severity) }.getOrNull()
        if (parsedSeverity == null) {
            _state.update { it.copy(surveyError = "Mức độ triệu chứng không hợp lệ.") }
            return
        }
        val symptoms = if (symptomCode == "NONE") {
            emptyList()
        } else {
            val code = runCatching { SymptomCode.valueOf(symptomCode) }.getOrNull()
            if (code == null) {
                _state.update { it.copy(surveyError = "Triệu chứng không hợp lệ.") }
                return
            }
            if (code == SymptomCode.OTHER && customDescription.isNullOrBlank()) {
                _state.update { it.copy(surveyError = "Mô tả triệu chứng trước khi gửi.") }
                return
            }
            val description = if (code == SymptomCode.OTHER) customDescription!!.trim() else code.displayLabel
            listOf(SurveySymptom(code = code, severity = parsedSeverity, description = description))
        }

        launchInSession { revision ->
            updateForSession(revision) {
                it.copy(isSubmittingSurvey = true, isSurveySubmitted = false, surveyError = null)
            }
            runCatching { repository.submitHealthSurvey(mood, symptoms) }
                .onSuccess { survey ->
                    val queuedOffline = survey.status == QUEUED_OFFLINE
                    updateForSession(revision) {
                        it.copy(
                            isSubmittingSurvey = false,
                            isSurveySubmitted = true,
                            message = if (queuedOffline) {
                                "Đã lưu khảo sát trên máy, chờ đồng bộ khi có mạng"
                            } else if (parsedSeverity == SurveySeverity.SEVERE && symptoms.isNotEmpty()) {
                                "Đã gửi khảo sát và cảnh báo triệu chứng nghiêm trọng"
                            } else {
                                "Đã gửi khảo sát sức khỏe"
                            },
                        )
                    }
                }
                .onFailure { error ->
                    updateForSession(revision) {
                        it.copy(
                            isSubmittingSurvey = false,
                            surveyError = error.toVietnameseUiMessage("Không gửi được khảo sát."),
                        )
                    }
                }
        }
    }

    fun clearSurveyStatus() {
        _state.update { it.copy(isSurveySubmitted = false, surveyError = null) }
    }

    fun createSos() {
        if (_state.value.sosStatus == SosSubmissionStatus.SENDING) return
        launchInSession { revision ->
            updateForSession(revision) {
                it.copy(sosStatus = SosSubmissionStatus.SENDING, sosError = null)
            }
            runCatching {
                repository.createSos(message = "SOS từ ứng dụng bệnh nhân", shareLocation = false)
            }.onSuccess { alert ->
                val queuedOffline = alert.status == QUEUED_OFFLINE
                updateForSession(revision) {
                    it.copy(
                        sosStatus = if (queuedOffline) {
                            SosSubmissionStatus.QUEUED_OFFLINE
                        } else {
                            SosSubmissionStatus.SENT
                        },
                        message = if (queuedOffline) {
                            "Đã lưu yêu cầu SOS trên máy, CHƯA gửi được do mất mạng. Nếu đang khẩn cấp, hãy gọi 115 ngay."
                        } else {
                            "Cảnh báo SOS đã được hệ thống ghi nhận"
                        },
                    )
                }
            }.onFailure { error ->
                updateForSession(revision) {
                    it.copy(
                        sosStatus = SosSubmissionStatus.FAILED,
                        sosError = error.toVietnameseUiMessage(
                            "Không gửi được SOS. Hãy gọi cấp cứu ngay nếu cần trợ giúp khẩn cấp.",
                        ),
                    )
                }
            }
        }
    }

    fun clearSosStatus() {
        _state.update { it.copy(sosStatus = SosSubmissionStatus.IDLE, sosError = null) }
    }

    fun loadMedicationDetail(medicationId: String?, forceRefresh: Boolean = false) {
        if (medicationId.isNullOrBlank()) {
            _state.update { it.copy(medicationDetailError = "Thuốc này chưa có mã danh mục để tra cứu.") }
            return
        }
        if (!forceRefresh && _state.value.medicationDetailId == medicationId && _state.value.medicationDetail != null) {
            return
        }
        launchInSession { revision ->
            updateForSession(revision) {
                it.copy(
                    medicationDetailId = medicationId,
                    medicationDetail = null,
                    isLoadingMedicationDetail = true,
                    medicationDetailError = null,
                )
            }
            runCatching { repository.getMedicationDetail(medicationId) }
                .onSuccess { detail ->
                    updateForSession(revision) {
                        if (it.medicationDetailId == medicationId) {
                            it.copy(medicationDetail = detail, isLoadingMedicationDetail = false)
                        } else {
                            it
                        }
                    }
                }
                .onFailure { error ->
                    updateForSession(revision) {
                        if (it.medicationDetailId == medicationId) {
                            it.copy(
                                isLoadingMedicationDetail = false,
                                medicationDetailError = error.toVietnameseUiMessage(
                                    "Không tải được thông tin thuốc.",
                                ),
                            )
                        } else {
                            it
                        }
                    }
                }
        }
    }

    fun loadCaregivers() {
        launchInSession { revision ->
            updateForSession(revision) {
                it.copy(isLoadingCaregivers = true, caregiverError = null)
            }
            runCatching { repository.getCaregivers() }
                .onSuccess { caregivers ->
                    updateForSession(revision) {
                        it.copy(caregivers = caregivers, isLoadingCaregivers = false)
                    }
                }
                .onFailure { error ->
                    updateForSession(revision) {
                        it.copy(
                            isLoadingCaregivers = false,
                            caregiverError = error.toVietnameseUiMessage(
                                "Không tải được danh sách người chăm sóc.",
                            ),
                        )
                    }
                }
        }
    }

    fun addCaregiver(phone: String, relationship: String?) {
        if (_state.value.isAddingCaregiver) return
        launchInSession { revision ->
            updateForSession(revision) {
                it.copy(
                    isAddingCaregiver = true,
                    caregiverError = null,
                    createdCaregiverTemporaryPin = null,
                    createdCaregiverInvite = null,
                )
            }
            runCatching { repository.createCaregiver(phone, relationship?.takeIf(String::isNotBlank)) }
                .onSuccess { created ->
                    updateForSession(revision) {
                        it.copy(
                            caregivers = listOf(created) + it.caregivers.filterNot { link -> link.id == created.id },
                            isAddingCaregiver = false,
                            createdCaregiverInvite = created.linkCode?.let { code ->
                                CreatedCaregiverInvite(
                                    linkCode = code,
                                    telegramDeepLink = created.telegramDeepLink,
                                )
                            },
                            message = if (created.status == QUEUED_OFFLINE) {
                                "Đã lưu người chăm sóc trên máy, chờ đồng bộ khi có mạng"
                            } else {
                                "Đã thêm người chăm sóc"
                            },
                        )
                    }
                }
                .onFailure { error ->
                    updateForSession(revision) {
                        it.copy(
                            isAddingCaregiver = false,
                            caregiverError = error.toVietnameseUiMessage("Không thêm được người chăm sóc."),
                        )
                    }
                }
        }
    }

    fun deleteCaregiver(linkId: String) {
        if (_state.value.deletingCaregiverId != null) return
        launchInSession { revision ->
            updateForSession(revision) {
                it.copy(deletingCaregiverId = linkId, caregiverError = null)
            }
            runCatching { repository.deleteCaregiver(linkId) }
                .onSuccess {
                    updateForSession(revision) { state ->
                        state.copy(
                            caregivers = state.caregivers.filterNot { it.id == linkId },
                            deletingCaregiverId = null,
                            message = "Đã gỡ liên kết người chăm sóc",
                        )
                    }
                }
                .onFailure { error ->
                    updateForSession(revision) {
                        it.copy(
                            deletingCaregiverId = null,
                            caregiverError = error.toVietnameseUiMessage(
                                "Không gỡ được người chăm sóc.",
                            ),
                        )
                    }
                }
        }
    }

    fun clearCaregiverError() {
        _state.update {
            it.copy(
                caregiverError = null,
                createdCaregiverTemporaryPin = null,
                createdCaregiverInvite = null,
            )
        }
    }

    fun loadAdherenceHistory(resetPage: Boolean = true) {
        val weekStart = _state.value.historyWeekStart
        val today = LocalDate.now()
        val weekEnd = minOf(weekStart.plusDays(6), today)
        if (weekStart > today) return
        val page = if (resetPage) 1 else _state.value.historyPage + 1
        launchInSession { revision ->
            updateForSession(revision) {
                it.copy(
                    isLoadingHistory = resetPage,
                    isLoadingMoreHistory = !resetPage,
                    historyError = null,
                )
            }
            runCatching {
                val summary = repository.getAdherenceSummary(weekStart, weekEnd)
                val logs = repository.getAdherenceLogs(weekStart, weekEnd, page = page)
                summary to logs
            }.onSuccess { (summary, logs) ->
                updateForSession(revision) {
                    if (it.historyWeekStart == weekStart) {
                        it.copy(
                            historySummary = summary,
                            historyLogs = if (resetPage) logs.content else it.historyLogs + logs.content,
                            historyPage = logs.page,
                            historyHasMore = !logs.isLast,
                            isLoadingHistory = false,
                            isLoadingMoreHistory = false,
                        )
                    } else {
                        it
                    }
                }
            }.onFailure { error ->
                updateForSession(revision) {
                    if (it.historyWeekStart == weekStart) {
                        it.copy(
                            isLoadingHistory = false,
                            isLoadingMoreHistory = false,
                            historyError = error.toVietnameseUiMessage(
                                "Không tải được lịch sử dùng thuốc.",
                            ),
                        )
                    } else {
                        it
                    }
                }
            }
        }
    }

    fun previousAdherenceWeek() {
        _state.update { it.copy(historyWeekStart = it.historyWeekStart.minusWeeks(1)) }
        loadAdherenceHistory()
    }

    fun nextAdherenceWeek() {
        val next = _state.value.historyWeekStart.plusWeeks(1)
        if (next > currentWeekStart()) return
        _state.update { it.copy(historyWeekStart = next) }
        loadAdherenceHistory()
    }

    fun loadMoreAdherenceHistory() {
        if (!_state.value.historyHasMore || _state.value.isLoadingMoreHistory) return
        loadAdherenceHistory(resetPage = false)
    }

    fun clearMessage() {
        _state.update { it.copy(message = null) }
    }

    private fun showHome(
        home: PatientHome,
        message: String? = _state.value.message,
        revision: Long,
    ) {
        updateForSession(revision) {
            it.copy(
                isLoading = false,
                error = null,
                routine = home.routine.ifEmpty { defaultRoutine() },
                doses = home.doses,
                medications = home.medications,
                adherence = home.adherence,
                adherenceRate = home.adherenceRate,
                busyDoseIds = emptySet(),
                message = message,
            )
        }
    }

    private fun launchInSession(block: suspend (revision: Long) -> Unit) {
        if (activePatientId == null) return
        val revision = sessionRevision
        val job = viewModelScope.launch(start = CoroutineStart.LAZY) { block(revision) }
        sessionJobs += job
        job.invokeOnCompletion { sessionJobs -= job }
        job.start()
    }

    private fun updateForSession(
        revision: Long,
        transform: (PatientUiState) -> PatientUiState,
    ) {
        if (isCurrentSession(revision)) _state.update(transform)
    }

    private fun isCurrentSession(revision: Long): Boolean =
        activePatientId != null && revision == sessionRevision

    private fun invalidateSession() {
        sessionRevision += 1
        pendingSyncJob?.cancel()
        pendingSyncJob = null
        val jobs = synchronized(sessionJobs) {
            sessionJobs.toList().also { sessionJobs.clear() }
        }
        jobs.forEach { it.cancel() }
    }

    private fun startPendingSyncCountCollection() {
        val revision = sessionRevision
        pendingSyncJob = viewModelScope.launch {
            repository.observePendingSyncCount().collect { count ->
                updateForSession(revision) { it.copy(pendingSyncCount = count) }
            }
        }
    }

    private fun monitorConnectivityRestored() {
        viewModelScope.launch {
            var wasOnline = connectivityObserver.isOnline.value
            connectivityObserver.isOnline.collect { online ->
                if (!wasOnline && online) outboxSyncScheduler.onConnectivityRestored()
                wasOnline = online
            }
        }
    }

    private fun String.isValidTime(): Boolean {
        val parts = split(':')
        if (parts.size != 2 || parts.any { it.length != 2 || !it.all(Char::isDigit) }) return false
        val hour = parts[0].toInt()
        val minute = parts[1].toInt()
        return hour in 0..23 && minute in 0..59
    }

    private companion object {
        const val QUEUED_OFFLINE = "QUEUED_OFFLINE"
    }
}
