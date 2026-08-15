package com.remindrx.app.ui.feature.patient

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
import com.remindrx.app.data.repository.PatientHome
import com.remindrx.app.data.repository.PatientRepository
import com.remindrx.app.testing.MainDispatcherRule
import java.time.LocalDate
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
        assertFalse(viewModel.state.value.needsRoutineOnboarding)
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
    fun `partial backend routine still requires routine onboarding`() {
        val repository = FakePatientRepository().apply {
            routineResponse = routineAt("", "07:10", "11:45", "18:15", "22:30")
        }
        val viewModel = PatientViewModel(repository)

        viewModel.startSession("patient-1")

        assertTrue(viewModel.state.value.routineCheckCompleted)
        assertTrue(viewModel.state.value.needsRoutineOnboarding)
        assertEquals(0, repository.loadHomeCalls)
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
        assertTrue(viewModel.state.value.needsRoutineOnboarding)
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
        error("Not used")

    override suspend fun getMedicationDetail(medicationId: String): MedicationDetail =
        error("Not used")

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
