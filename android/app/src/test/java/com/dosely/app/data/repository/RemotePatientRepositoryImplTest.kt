package com.dosely.app.data.repository

import com.google.gson.FieldNamingPolicy
import com.google.gson.Gson
import com.google.gson.GsonBuilder
import com.dosely.app.data.AdherenceSummary
import com.dosely.app.data.AgentRun
import com.dosely.app.data.AgentRunPollResult
import com.dosely.app.data.AgentRunRequest
import com.dosely.app.data.DoseAction
import com.dosely.app.data.DoseStatus
import com.dosely.app.data.RoutineItem
import com.dosely.app.data.RoutineUpdateResult
import com.dosely.app.data.local.dao.OutboxDao
import com.dosely.app.data.local.dao.PatientCacheDao
import com.dosely.app.data.local.entity.AdherenceSummaryEntity
import com.dosely.app.data.local.entity.DoseTodayEntity
import com.dosely.app.data.local.entity.MedicationEntity
import com.dosely.app.data.local.entity.OutboxActionEntity
import com.dosely.app.data.local.entity.OutboxActionType
import com.dosely.app.data.local.entity.OutboxStatus
import com.dosely.app.data.local.entity.RoutineItemEntity
import com.dosely.app.data.remote.DoselyApiService
import java.time.LocalDate
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.runBlocking
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import okhttp3.mockwebserver.SocketPolicy
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import retrofit2.HttpException
import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory

class RemotePatientRepositoryImplTest {
    private lateinit var server: MockWebServer
    private lateinit var cacheDao: FakePatientCacheDao
    private lateinit var outboxDao: FakeOutboxDao
    private lateinit var scheduler: RecordingOutboxSyncScheduler
    private lateinit var repository: RemotePatientRepositoryImpl
    private val gson: Gson = GsonBuilder()
        .setFieldNamingPolicy(FieldNamingPolicy.LOWER_CASE_WITH_UNDERSCORES)
        .create()

    @Before
    fun setUp() {
        server = MockWebServer()
        server.start()
        cacheDao = FakePatientCacheDao()
        outboxDao = FakeOutboxDao()
        scheduler = RecordingOutboxSyncScheduler()
        val api = Retrofit.Builder()
            .baseUrl(server.url("api/v1/"))
            .addConverterFactory(GsonConverterFactory.create(gson))
            .build()
            .create(DoselyApiService::class.java)
        repository = RemotePatientRepositoryImpl(
            api = api,
            sessionStore = SessionStore(FakeSessionPersistence(testSession())),
            routineRepository = FakeRoutineRepository(),
            patientCacheDao = cacheDao,
            outboxDao = outboxDao,
            outboxSyncScheduler = scheduler,
            gson = gson,
        )
    }

    @After
    fun tearDown() {
        server.shutdown()
    }

    @Test
    fun `record dose action sends online request without enqueueing outbox`() = runBlocking {
        server.enqueue(
            success(
                """
                {
                  "id": "log-1",
                  "scheduled_dose_id": "dose-1",
                  "patient_id": "patient-1",
                  "action": "TAKEN",
                  "performed_at": "2026-08-28T00:00:00Z",
                  "action_source": "PATIENT_MOBILE_APP",
                  "payload": {},
                  "idempotency_key": "server-key"
                }
                """.trimIndent(),
            ),
        )

        repository.recordDoseAction("dose-1", DoseAction.TAKEN)

        val request = server.takeRequest()
        assertEquals("POST", request.method)
        assertEquals("/api/v1/scheduled-doses/dose-1/actions", request.requestUrl?.encodedPath)
        assertTrue(request.getHeader("Idempotency-Key").orEmpty().isNotBlank())
        assertEquals(emptyList<OutboxActionEntity>(), outboxDao.pendingActions)
        assertEquals(0, scheduler.scheduleCalls)
        assertEquals(DoseStatus.TAKEN, cacheDao.updatedDoseStatuses["dose-1"])
    }

    @Test
    fun `record dose action queues only when connectivity fails`() = runBlocking {
        server.enqueue(MockResponse().setSocketPolicy(SocketPolicy.DISCONNECT_AT_START))

        val result = repository.recordDoseAction("dose-1", DoseAction.SKIPPED, note = "Không thấy đói")

        assertEquals("dose-1", result.scheduledDoseId)
        assertEquals("SKIPPED", result.action)
        assertEquals(1, outboxDao.pendingActions.size)
        assertEquals(OutboxActionType.RECORD_DOSE_ACTION, outboxDao.pendingActions.single().actionType)
        assertEquals(1, scheduler.scheduleCalls)
        assertEquals(DoseStatus.SKIPPED, cacheDao.updatedDoseStatuses["dose-1"])
    }

    @Test
    fun `record dose action does not enqueue validation errors`() = runBlocking {
        server.enqueue(
            MockResponse()
                .setResponseCode(422)
                .setHeader("Content-Type", "application/json")
                .setBody("""{"success":false,"code":422,"message":"invalid","data":null,"errors":null}"""),
        )

        val error = runCatching { repository.recordDoseAction("dose-1", DoseAction.TAKEN) }.exceptionOrNull()

        assertTrue(error is HttpException)
        assertEquals(emptyList<OutboxActionEntity>(), outboxDao.pendingActions)
        assertEquals(0, scheduler.scheduleCalls)
    }

    private fun success(data: String): MockResponse = MockResponse()
        .setResponseCode(200)
        .setHeader("Content-Type", "application/json")
        .setBody(
            """
            {
              "success": true,
              "code": 200,
              "message": "ok",
              "data": $data,
              "errors": null
            }
            """.trimIndent(),
        )
}

private class FakePatientCacheDao : PatientCacheDao() {
    val updatedDoseStatuses = mutableMapOf<String, DoseStatus>()
    private val routines = mutableListOf<RoutineItemEntity>()
    private val doses = mutableListOf<DoseTodayEntity>()
    private val medications = mutableListOf<MedicationEntity>()
    private val summaries = mutableListOf<AdherenceSummaryEntity>()

    override suspend fun getRoutine(patientId: String): List<RoutineItemEntity> =
        routines.filter { it.patientId == patientId }

    override suspend fun getDoses(patientId: String, scheduleDate: String): List<DoseTodayEntity> =
        doses.filter { it.patientId == patientId && it.scheduleDate == scheduleDate }

    override suspend fun getMedications(patientId: String): List<MedicationEntity> =
        medications.filter { it.patientId == patientId }

    override suspend fun getAdherenceSummary(
        patientId: String,
        fromDate: String,
        toDate: String,
    ): AdherenceSummaryEntity? =
        summaries.firstOrNull { it.patientId == patientId && it.fromDate == fromDate && it.toDate == toDate }

    override suspend fun insertRoutine(items: List<RoutineItemEntity>) {
        routines += items
    }

    override suspend fun insertDoses(doses: List<DoseTodayEntity>) {
        this.doses += doses
    }

    override suspend fun insertMedications(medications: List<MedicationEntity>) {
        this.medications += medications
    }

    override suspend fun insertAdherenceSummary(summary: AdherenceSummaryEntity) {
        summaries += summary
    }

    override suspend fun deleteRoutine(patientId: String) {
        routines.removeAll { it.patientId == patientId }
    }

    override suspend fun deleteDoses(patientId: String, scheduleDate: String) {
        doses.removeAll { it.patientId == patientId && it.scheduleDate == scheduleDate }
    }

    override suspend fun deleteMedications(patientId: String) {
        medications.removeAll { it.patientId == patientId }
    }

    override suspend fun deleteAdherenceSummaries(patientId: String) {
        summaries.removeAll { it.patientId == patientId }
    }

    override suspend fun deleteAllRoutineForPatient(patientId: String) = deleteRoutine(patientId)

    override suspend fun deleteAllDosesForPatient(patientId: String) {
        doses.removeAll { it.patientId == patientId }
    }

    override suspend fun deleteAllMedicationsForPatient(patientId: String) = deleteMedications(patientId)

    override suspend fun updateDoseStatus(patientId: String, doseId: String, status: DoseStatus) {
        updatedDoseStatuses[doseId] = status
    }
}

private class FakeOutboxDao : OutboxDao() {
    private val pendingFlow = MutableStateFlow(emptyList<OutboxActionEntity>())
    val pendingActions: List<OutboxActionEntity>
        get() = pendingFlow.value

    override suspend fun insert(action: OutboxActionEntity) {
        pendingFlow.value = pendingFlow.value + action
    }

    override suspend fun deletePendingByType(
        patientId: String,
        actionType: OutboxActionType,
        status: OutboxStatus,
    ) {
        pendingFlow.value = pendingFlow.value.filterNot {
            it.patientId == patientId && it.actionType == actionType && it.status == status
        }
    }

    override fun observePending(patientId: String, status: OutboxStatus): Flow<List<OutboxActionEntity>> =
        pendingFlow

    override fun observePendingCount(patientId: String, status: OutboxStatus): Flow<Int> =
        MutableStateFlow(pendingFlow.value.count { it.patientId == patientId && it.status == status })

    override suspend fun getPendingOnce(patientId: String, status: OutboxStatus): List<OutboxActionEntity> =
        pendingFlow.value
            .filter { it.patientId == patientId && it.status == status }
            .sortedBy { it.createdAt }

    override suspend fun delete(id: String) {
        pendingFlow.value = pendingFlow.value.filterNot { it.id == id }
    }

    override suspend fun recordAttemptFailure(id: String, attemptCount: Int, attemptedAt: Long, lastError: String?) {
        pendingFlow.value = pendingFlow.value.map {
            if (it.id == id) {
                it.copy(attemptCount = attemptCount, lastAttemptAt = attemptedAt, lastError = lastError)
            } else {
                it
            }
        }
    }

    override suspend fun markFailedTerminal(id: String, attemptedAt: Long, lastError: String?) {
        pendingFlow.value = pendingFlow.value.map {
            if (it.id == id) {
                it.copy(status = OutboxStatus.FAILED, lastAttemptAt = attemptedAt, lastError = lastError)
            } else {
                it
            }
        }
    }
}

private class RecordingOutboxSyncScheduler : OutboxSyncScheduler {
    var scheduleCalls = 0
    var connectivityRestoredCalls = 0

    override fun scheduleSync() {
        scheduleCalls += 1
    }

    override fun onConnectivityRestored() {
        connectivityRestoredCalls += 1
    }
}

private class FakeRoutineRepository : RoutineRepository {
    override suspend fun getRoutine(): List<RoutineItem> = emptyList()
    override suspend fun updateRoutine(routine: List<RoutineItem>): List<RoutineItem> = routine
    override suspend fun requestReschedule(reason: String?): AgentRunRequest = error("Not used")
    override suspend fun getAgentRunStatus(agentRunId: String): AgentRun = error("Not used")
    override suspend fun awaitAgentRun(
        agentRunId: String,
        pollIntervalMillis: Long,
        timeoutMillis: Long,
    ): AgentRunPollResult = error("Not used")

    override suspend fun updateRoutineAndReschedule(
        routine: List<RoutineItem>,
        reason: String?,
    ): RoutineUpdateResult = error("Not used")
}

private fun testSession(): AuthSession = AuthSession(
    accessToken = "access",
    refreshToken = "refresh",
    patientId = "patient-1",
    mustChangePassword = false,
    needOnboarding = false,
    phone = "+84901234567",
)
