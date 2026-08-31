package com.remindrx.app.ui.feature.patient

import com.remindrx.app.core.PatientRealtimeEvent
import com.remindrx.app.core.PatientRealtimeEventType
import com.remindrx.app.core.PatientRealtimeEvents
import com.remindrx.app.core.connectivity.AlwaysOnlineConnectivityObserver
import com.remindrx.app.data.AdherenceLog
import com.remindrx.app.data.AdherenceSummary
import com.remindrx.app.data.Alert
import com.remindrx.app.data.CaregiverLink
import com.remindrx.app.data.DoseAction
import com.remindrx.app.data.HealthSurvey
import com.remindrx.app.data.MedicationDetail
import com.remindrx.app.data.OnboardingResult
import com.remindrx.app.data.PageResult
import com.remindrx.app.data.PatientSex
import com.remindrx.app.data.RoutineItem
import com.remindrx.app.data.RoutineUpdateResult
import com.remindrx.app.data.ScheduleUpdateStatus
import com.remindrx.app.data.SurveySymptom
import com.remindrx.app.data.repository.NoOpOutboxSyncScheduler
import com.remindrx.app.data.repository.PatientHome
import com.remindrx.app.data.repository.PatientRepository
import com.remindrx.app.testing.MainDispatcherRule
import java.time.LocalDate
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.asSharedFlow
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.ResponseBody.Companion.toResponseBody
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import retrofit2.HttpException
import retrofit2.Response

class PatientViewModelTest {
    @get:Rule
    val mainDispatcherRule = MainDispatcherRule()

    @Test
    fun `repository is untouched before session then valid session loads dashboard`() {
        val routine = routineAt("06:10", "07:10", "11:45", "18:15", "22:30")
        val repository = FakePatientRepository().apply {
            routineResponse = routine
            homeResponse = patientHome(routine, adherenceRate = 87.6f)
        }
        val viewModel = PatientViewModel(repository)

        viewModel.refresh()

        assertEquals(0, repository.getRoutineCalls)
        assertEquals(0, repository.loadHomeCalls)
        assertFalse(viewModel.state.value.routineCheckCompleted)

        viewModel.startSession("patient-1")

        assertEquals(1, repository.getRoutineCalls)
        assertEquals(1, repository.loadHomeCalls)
        assertTrue(viewModel.state.value.routineCheckCompleted)
        assertFalse(viewModel.state.value.isLoading)
        assertEquals(routine, viewModel.state.value.routine)
        assertEquals(88, viewModel.state.value.adherenceRate)

        viewModel.startSession("patient-1")
        assertEquals(1, repository.getRoutineCalls)
        assertEquals(1, repository.loadHomeCalls)
    }

    @Test
    fun `onboarding keeps saved routine when reschedule fails`() {
        verifyOnboardingRoutineIsKept(
            status = ScheduleUpdateStatus.FAILED,
            backendError = "Rescheduling agent failed",
            expectedMessage = "Đã lưu thói quen nhưng chưa cập nhật được lịch thuốc",
            expectedRoutineError = "Rescheduling agent failed",
        )
    }

    @Test
    fun `partial backend routine falls back to defaults for invalid entries`() {
        val repository = FakePatientRepository().apply {
            routineResponse = routineAt("", "07:10", "11:45", "18:15", "22:30")
        }
        val viewModel = PatientViewModel(repository)

        viewModel.startSession("patient-1")

        assertTrue(viewModel.state.value.routineCheckCompleted)
        assertEquals(1, repository.loadHomeCalls)
        assertEquals("06:30", viewModel.state.value.routine.first { it.key == "wake_time" }.time)
    }

    @Test
    fun `onboarding keeps saved routine when reschedule times out`() {
        verifyOnboardingRoutineIsKept(
            status = ScheduleUpdateStatus.TIMED_OUT,
            backendError = "Agent polling timed out",
            expectedMessage = "Đã lưu thói quen; lịch thuốc vẫn đang được cập nhật",
            expectedRoutineError = null,
        )
    }

    @Test
    fun `queued offline sos uses explicit emergency message`() {
        val repository = FakePatientRepository().apply {
            sosResponse = Alert(
                id = "sos-local-1",
                patientId = "patient-1",
                assignedDoctorId = null,
                triggeredByType = "PATIENT",
                alertType = "SOS",
                severity = "CRITICAL",
                status = "QUEUED_OFFLINE",
                message = "SOS từ ứng dụng bệnh nhân",
                createdAt = "2026-08-28T00:00:00Z",
            )
        }
        val viewModel = PatientViewModel(repository)
        viewModel.startSession("patient-1")

        viewModel.createSos()

        assertEquals(SosSubmissionStatus.QUEUED_OFFLINE, viewModel.state.value.sosStatus)
        assertEquals(
            "Đã lưu yêu cầu SOS trên máy, CHƯA gửi được do mất mạng. Nếu đang khẩn cấp, hãy gọi 115 ngay.",
            viewModel.state.value.message,
        )
    }

    @Test
    fun `ROUTINE_UPDATED reloads only the routine, not the whole dashboard`() {
        val routine = routineAt("06:10", "07:10", "11:45", "18:15", "22:30")
        val repository = FakePatientRepository().apply {
            routineResponse = routine
            homeResponse = patientHome(routine)
        }
        val realtimeEvents = FakePatientRealtimeEvents()
        val viewModel = PatientViewModel(
            repository,
            realtimeEvents,
            AlwaysOnlineConnectivityObserver,
            NoOpOutboxSyncScheduler(),
        )
        viewModel.startSession("patient-1")
        assertEquals(1, repository.getRoutineCalls)
        assertEquals(1, repository.loadHomeCalls)

        val updatedRoutine = routineAt("06:45", "07:10", "11:45", "18:15", "22:30")
        repository.routineResponse = updatedRoutine
        realtimeEvents.emit(PatientRealtimeEventType.ROUTINE_UPDATED)

        assertEquals(2, repository.getRoutineCalls)
        assertEquals(1, repository.loadHomeCalls)
        assertEquals(updatedRoutine, viewModel.state.value.routine)
    }

    @Test
    fun `SCHEDULE_UPDATED reloads the dashboard, not just the routine`() {
        val routine = routineAt("06:10", "07:10", "11:45", "18:15", "22:30")
        val repository = FakePatientRepository().apply {
            routineResponse = routine
            homeResponse = patientHome(routine, adherenceRate = 50f)
        }
        val realtimeEvents = FakePatientRealtimeEvents()
        val viewModel = PatientViewModel(
            repository,
            realtimeEvents,
            AlwaysOnlineConnectivityObserver,
            NoOpOutboxSyncScheduler(),
        )
        viewModel.startSession("patient-1")
        assertEquals(1, repository.getRoutineCalls)
        assertEquals(1, repository.loadHomeCalls)
        assertEquals(50, viewModel.state.value.adherenceRate)

        repository.homeResponse = patientHome(routine, adherenceRate = 92f)
        realtimeEvents.emit(PatientRealtimeEventType.SCHEDULE_UPDATED)

        assertEquals(1, repository.getRoutineCalls)
        assertEquals(2, repository.loadHomeCalls)
        assertEquals(92, viewModel.state.value.adherenceRate)
    }

    @Test
    fun `realtime events before any session starts are ignored`() {
        val repository = FakePatientRepository()
        val realtimeEvents = FakePatientRealtimeEvents()
        PatientViewModel(repository, realtimeEvents, AlwaysOnlineConnectivityObserver, NoOpOutboxSyncScheduler())

        realtimeEvents.emit(PatientRealtimeEventType.ROUTINE_UPDATED)
        realtimeEvents.emit(PatientRealtimeEventType.SCHEDULE_UPDATED)

        assertEquals(0, repository.getRoutineCalls)
        assertEquals(0, repository.loadHomeCalls)
    }

    @Test
    fun `medication detail is cached until force refresh is requested`() {
        val repository = FakePatientRepository().apply {
            medicationDetailResponses = mutableListOf(
                medicationDetail("med-1", "Metformin"),
                medicationDetail("med-1", "Metformin XR"),
            )
        }
        val viewModel = PatientViewModel(repository)
        viewModel.startSession("patient-1")

        viewModel.loadMedicationDetail("med-1")
        viewModel.loadMedicationDetail("med-1")

        assertEquals(1, repository.getMedicationDetailCalls)
        assertEquals("Metformin", viewModel.state.value.medicationDetail?.name)

        viewModel.loadMedicationDetail("med-1", forceRefresh = true)

        assertEquals(2, repository.getMedicationDetailCalls)
        assertEquals("Metformin XR", viewModel.state.value.medicationDetail?.name)
    }

    private fun verifyOnboardingRoutineIsKept(
        status: ScheduleUpdateStatus,
        backendError: String,
        expectedMessage: String,
        expectedRoutineError: String?,
    ) {
        val submitted = routineAt("05:50", "06:30", "12:05", "19:10", "23:00")
        val repository = FakePatientRepository().apply {
            routineFailure = notFound()
            routineUpdateStatus = status
            routineUpdateError = backendError
        }
        val viewModel = PatientViewModel(repository)
        viewModel.startSession("patient-1")
        assertEquals(0, repository.loadHomeCalls)

        viewModel.saveRoutine(submitted)

        assertEquals(1, repository.updateRoutineCalls)
        assertEquals(submitted, repository.lastSubmittedRoutine)
        assertEquals(1, repository.loadHomeCalls)
        assertEquals(submitted, viewModel.state.value.routine)
        assertTrue(viewModel.state.value.routineSaveCompleted)
        assertFalse(viewModel.state.value.isSavingRoutine)
        assertEquals(expectedMessage, viewModel.state.value.message)
        assertEquals(expectedRoutineError, viewModel.state.value.routineError)
    }

    private fun notFound(): HttpException = HttpException(
        Response.error<Unit>(
            404,
            "{}".toResponseBody("application/json".toMediaType()),
        ),
    )
}

/** UnconfinedTestDispatcher (see [MainDispatcherRule]) makes emit() deliver synchronously. */
private class FakePatientRealtimeEvents : PatientRealtimeEvents {
    private val flow = MutableSharedFlow<PatientRealtimeEvent>(extraBufferCapacity = 8)
    override val events: SharedFlow<PatientRealtimeEvent> = flow.asSharedFlow()

    fun emit(type: PatientRealtimeEventType) {
        check(flow.tryEmit(PatientRealtimeEvent(type))) { "event buffer full" }
    }
}

private class FakePatientRepository : PatientRepository {
    var getRoutineCalls = 0
    var loadHomeCalls = 0
    var updateRoutineCalls = 0
    var lastSubmittedRoutine: List<RoutineItem>? = null
    var routineResponse: List<RoutineItem> = routineAt("06:30", "07:00", "11:30", "18:00", "22:00")
    var routineFailure: Throwable? = null
    var routineUpdateStatus: ScheduleUpdateStatus = ScheduleUpdateStatus.UPDATED
    var routineUpdateError: String? = null
    var homeResponse: PatientHome = patientHome(routineResponse)
    var pendingSyncCountFlow = MutableStateFlow(0)
    var sosResponse: Alert? = null
    var getMedicationDetailCalls = 0
    var medicationDetailResponses = mutableListOf<MedicationDetail>()

    override suspend fun getRoutine(): List<RoutineItem> {
        getRoutineCalls += 1
        routineFailure?.let { throw it }
        return routineResponse
    }

    override suspend fun loadHome(): PatientHome {
        loadHomeCalls += 1
        val saved = lastSubmittedRoutine
        return if (saved == null) homeResponse else patientHome(saved)
    }

    override fun observePendingSyncCount(): Flow<Int> = pendingSyncCountFlow

    override suspend fun onboard(
        name: String,
        routine: List<RoutineItem>,
        dob: LocalDate?,
        sex: PatientSex?,
        emergencyNote: String?,
        timezone: String,
    ): OnboardingResult = error("Not used")

    override suspend fun updateRoutine(routine: List<RoutineItem>): RoutineUpdateResult {
        updateRoutineCalls += 1
        lastSubmittedRoutine = routine
        return RoutineUpdateResult(
            routine = routine,
            scheduleStatus = routineUpdateStatus,
            errorMessage = routineUpdateError,
        )
    }

    override suspend fun recordDoseAction(
        doseId: String,
        action: DoseAction,
        note: String?,
    ): AdherenceLog = error("Not used")

    override suspend fun submitHealthSurvey(
        mood: Int,
        symptoms: List<SurveySymptom>,
        surveyDate: LocalDate,
    ): HealthSurvey = error("Not used")

    override suspend fun createSos(message: String?, shareLocation: Boolean): Alert =
        sosResponse ?: error("Not used")

    override suspend fun getMedicationDetail(medicationId: String): MedicationDetail {
        getMedicationDetailCalls += 1
        return medicationDetailResponses.removeFirstOrNull() ?: error("Not used")
    }

    override suspend fun getCaregivers(): List<CaregiverLink> = error("Not used")

    override suspend fun createCaregiver(
        caregiverPhone: String,
        relationship: String?,
        channels: List<String>,
    ): CaregiverLink = error("Not used")

    override suspend fun deleteCaregiver(caregiverLinkId: String): String = error("Not used")

    override suspend fun getAdherenceSummary(from: LocalDate, to: LocalDate): AdherenceSummary =
        error("Not used")

    override suspend fun getAdherenceLogs(
        from: LocalDate,
        to: LocalDate,
        page: Int,
        size: Int,
    ): PageResult<AdherenceLog> = error("Not used")
}

private fun routineAt(
    wake: String,
    breakfast: String,
    lunch: String,
    dinner: String,
    sleep: String,
): List<RoutineItem> = listOf(
    RoutineItem("wake_time", "Thức dậy", wake),
    RoutineItem("breakfast_time", "Ăn sáng", breakfast),
    RoutineItem("lunch_time", "Ăn trưa", lunch),
    RoutineItem("dinner_time", "Ăn tối", dinner),
    RoutineItem("sleep_time", "Đi ngủ", sleep),
)

private fun patientHome(
    routine: List<RoutineItem>,
    adherenceRate: Float = 80f,
): PatientHome = PatientHome(
    routine = routine,
    doses = emptyList(),
    medications = emptyList(),
    adherence = AdherenceSummary(
        patientId = "patient-1",
        fromDate = LocalDate.of(2026, 8, 10),
        toDate = LocalDate.of(2026, 8, 14),
        adherenceRate = adherenceRate,
        totalDoses = 10,
        takenDoses = 8,
        skippedDoses = 1,
        missedDoses = 1,
    ),
)

private fun medicationDetail(id: String, name: String): MedicationDetail = MedicationDetail(
    id = id,
    name = name,
    composition = null,
    manufacturer = null,
    uses = null,
    sideEffects = null,
    imageUrl = null,
    sourceName = "Demo",
    isActive = true,
)
