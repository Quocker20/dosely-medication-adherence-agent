package com.remindrx.app.sync

import com.google.gson.FieldNamingPolicy
import com.google.gson.Gson
import com.google.gson.GsonBuilder
import com.remindrx.app.data.local.dao.PatientCacheDao
import com.remindrx.app.data.local.entity.AdherenceSummaryEntity
import com.remindrx.app.data.local.entity.CreateCaregiverPayload
import com.remindrx.app.data.local.entity.DeleteCaregiverPayload
import com.remindrx.app.data.local.entity.DoseTodayEntity
import com.remindrx.app.data.local.entity.MedicationEntity
import com.remindrx.app.data.local.entity.OutboxActionEntity
import com.remindrx.app.data.local.entity.OutboxActionType
import com.remindrx.app.data.local.entity.RecordDoseActionPayload
import com.remindrx.app.data.local.entity.RoutineItemEntity
import com.remindrx.app.data.local.entity.SubmitSurveyPayload
import com.remindrx.app.data.remote.RemindRxApiService
import java.util.UUID
import kotlinx.coroutines.runBlocking
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import okhttp3.mockwebserver.SocketPolicy
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory

class OutboxReplayerTest {
    private lateinit var server: MockWebServer
    private lateinit var cacheDao: FakePatientCacheDao
    private lateinit var replayer: OutboxReplayer
    private val gson: Gson = GsonBuilder()
        .setFieldNamingPolicy(FieldNamingPolicy.LOWER_CASE_WITH_UNDERSCORES)
        .create()

    private val patientId = "patient-1"

    @Before
    fun setUp() {
        server = MockWebServer()
        server.start()
        cacheDao = FakePatientCacheDao()
        val api = Retrofit.Builder()
            .baseUrl(server.url("api/v1/"))
            .addConverterFactory(GsonConverterFactory.create(gson))
            .build()
            .create(RemindRxApiService::class.java)
        replayer = OutboxReplayer(api = api, patientCacheDao = cacheDao, gson = gson)
    }

    @After
    fun tearDown() {
        server.shutdown()
    }

    @Test
    fun `record dose action synced on 200`() = runBlocking {
        server.enqueue(successEnvelope(adherenceLogJson()))

        val outcome = replayer.replay(patientId, doseActionRow())

        assertEquals(ReplayOutcome.Synced, outcome)
    }

    @Test
    fun `record dose action retryable on connection failure`() = runBlocking {
        server.enqueue(MockResponse().setSocketPolicy(SocketPolicy.DISCONNECT_AT_START))

        val outcome = replayer.replay(patientId, doseActionRow())

        assertEquals(ReplayOutcome.Retryable, outcome)
    }

    @Test
    fun `record dose action failed on validation error`() = runBlocking {
        server.enqueue(MockResponse().setResponseCode(422).setBody(errorEnvelope("Invalid action")))

        val outcome = replayer.replay(patientId, doseActionRow())

        assertTrue(outcome is ReplayOutcome.Failed)
    }

    @Test
    fun `submit survey conflict is kept for review, not silently assumed synced`() = runBlocking {
        // Per docs/outbox-replay-contract.md: a 409 here can mean "already submitted" or
        // "a different survey already exists for this date" — the client can't tell which
        // without fetching and diffing, so it must not silently discard the local one.
        server.enqueue(MockResponse().setResponseCode(409).setBody(errorEnvelope("already submitted")))

        val outcome = replayer.replay(patientId, surveyRow())

        assertTrue(outcome is ReplayOutcome.Failed)
    }

    @Test
    fun `submit survey validation error is not swallowed as synced`() = runBlocking {
        server.enqueue(MockResponse().setResponseCode(422).setBody(errorEnvelope("bad payload")))

        val outcome = replayer.replay(patientId, surveyRow())

        assertTrue(outcome is ReplayOutcome.Failed)
    }

    @Test
    fun `delete caregiver 404 is treated as already synced`() = runBlocking {
        server.enqueue(MockResponse().setResponseCode(404).setBody(errorEnvelope("not found")))

        val outcome = replayer.replay(patientId, deleteCaregiverRow())

        assertEquals(ReplayOutcome.Synced, outcome)
    }

    @Test
    fun `create caregiver conflict is kept for review, not silently assumed synced`() = runBlocking {
        server.enqueue(MockResponse().setResponseCode(409).setBody(errorEnvelope("already linked")))

        val outcome = replayer.replay(patientId, createCaregiverRow())

        assertTrue(outcome is ReplayOutcome.Failed)
    }

    @Test
    fun `update routine replays PUT then best-effort reschedule and updates cache`() = runBlocking {
        server.enqueue(successEnvelope(routineResponseJson()))
        // Reschedule request — allowed to fail without affecting the outcome.
        server.enqueue(MockResponse().setSocketPolicy(SocketPolicy.DISCONNECT_AT_START))

        val outcome = replayer.replay(patientId, routineRow())

        assertEquals(ReplayOutcome.Synced, outcome)
        assertEquals(1, cacheDao.routineWriteCount)
    }

    @Test
    fun `row for a different patient is never replayed`() = runBlocking {
        val outcome = replayer.replay(patientId, doseActionRow().copy(patientId = "someone-else"))

        assertEquals(ReplayOutcome.Retryable, outcome)
        assertEquals(0, server.requestCount)
    }

    private fun doseActionRow() = OutboxActionEntity(
        id = UUID.randomUUID().toString(),
        patientId = patientId,
        actionType = OutboxActionType.RECORD_DOSE_ACTION,
        payloadJson = gson.toJson(RecordDoseActionPayload(scheduledDoseId = "dose-1", action = "TAKEN", note = null)),
        createdAt = System.currentTimeMillis(),
    )

    private fun surveyRow() = OutboxActionEntity(
        id = UUID.randomUUID().toString(),
        patientId = patientId,
        actionType = OutboxActionType.SUBMIT_SURVEY,
        payloadJson = gson.toJson(SubmitSurveyPayload(mood = 4, symptoms = emptyList(), surveyDate = "2026-08-28")),
        createdAt = System.currentTimeMillis(),
    )

    private fun deleteCaregiverRow() = OutboxActionEntity(
        id = UUID.randomUUID().toString(),
        patientId = patientId,
        actionType = OutboxActionType.DELETE_CAREGIVER,
        payloadJson = gson.toJson(DeleteCaregiverPayload(caregiverLinkId = "link-1")),
        createdAt = System.currentTimeMillis(),
    )

    private fun createCaregiverRow() = OutboxActionEntity(
        id = UUID.randomUUID().toString(),
        patientId = patientId,
        actionType = OutboxActionType.CREATE_CAREGIVER,
        payloadJson = gson.toJson(
            CreateCaregiverPayload(caregiverPhone = "+84900111222", relationship = "Con gái", channels = listOf("SMS")),
        ),
        createdAt = System.currentTimeMillis(),
    )

    private fun routineRow() = OutboxActionEntity(
        id = UUID.randomUUID().toString(),
        patientId = patientId,
        actionType = OutboxActionType.UPDATE_ROUTINE,
        payloadJson = """{"routine":[
            {"key":"wake_time","label":"Thức dậy","time":"06:30"},
            {"key":"breakfast_time","label":"Ăn sáng","time":"07:00"},
            {"key":"lunch_time","label":"Ăn trưa","time":"12:00"},
            {"key":"dinner_time","label":"Ăn tối","time":"18:00"},
            {"key":"sleep_time","label":"Đi ngủ","time":"22:00"}
        ]}""",
        createdAt = System.currentTimeMillis(),
    )

    private fun successEnvelope(dataJson: String) = MockResponse().setResponseCode(200).setBody(
        """{"success":true,"code":200,"message":"ok","data":$dataJson}""",
    )

    private fun errorEnvelope(message: String) =
        """{"success":false,"code":0,"message":"$message","data":null}"""

    private fun adherenceLogJson() = """
        {"id":"log-1","scheduled_dose_id":"dose-1","patient_id":"$patientId","action":"TAKEN",
         "performed_at":"2026-08-28T00:00:00Z","action_source":"PATIENT_MOBILE_APP","payload":{},
         "idempotency_key":null}
    """.trimIndent()

    private fun routineResponseJson() = """
        {"id":"routine-1","patient_id":"$patientId","wake_time":"06:30","breakfast_time":"07:00",
         "lunch_time":"12:00","dinner_time":"18:00","sleep_time":"22:00","updated_at":"2026-08-28T00:00:00Z"}
    """.trimIndent()
}

private class FakePatientCacheDao : PatientCacheDao() {
    var routineWriteCount = 0
    private val routines = mutableListOf<RoutineItemEntity>()

    override suspend fun getRoutine(patientId: String): List<RoutineItemEntity> =
        routines.filter { it.patientId == patientId }

    override suspend fun getDoses(patientId: String, scheduleDate: String): List<DoseTodayEntity> = emptyList()
    override suspend fun getMedications(patientId: String): List<MedicationEntity> = emptyList()
    override suspend fun getAdherenceSummary(
        patientId: String,
        fromDate: String,
        toDate: String,
    ): AdherenceSummaryEntity? = null

    override suspend fun insertRoutine(items: List<RoutineItemEntity>) {
        routineWriteCount += 1
        routines += items
    }

    override suspend fun insertDoses(doses: List<DoseTodayEntity>) = Unit
    override suspend fun insertMedications(medications: List<MedicationEntity>) = Unit
    override suspend fun insertAdherenceSummary(summary: AdherenceSummaryEntity) = Unit

    override suspend fun deleteRoutine(patientId: String) {
        routines.removeAll { it.patientId == patientId }
    }

    override suspend fun deleteDoses(patientId: String, scheduleDate: String) = Unit
    override suspend fun deleteMedications(patientId: String) = Unit
    override suspend fun deleteAdherenceSummaries(patientId: String) = Unit
    override suspend fun deleteAllRoutineForPatient(patientId: String) = deleteRoutine(patientId)
    override suspend fun deleteAllDosesForPatient(patientId: String) = Unit
    override suspend fun deleteAllMedicationsForPatient(patientId: String) = Unit
    override suspend fun updateDoseStatus(
        patientId: String,
        doseId: String,
        status: com.remindrx.app.data.DoseStatus,
    ) = Unit
}
