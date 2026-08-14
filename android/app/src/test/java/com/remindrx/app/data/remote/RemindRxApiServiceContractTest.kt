package com.remindrx.app.data.remote

import com.google.gson.FieldNamingPolicy
import com.google.gson.GsonBuilder
import com.google.gson.JsonParser
import kotlinx.coroutines.runBlocking
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory

class RemindRxApiServiceContractTest {
    private lateinit var server: MockWebServer
    private lateinit var api: RemindRxApiService

    @Before
    fun setUp() {
        server = MockWebServer()
        server.start()
        val gson = GsonBuilder()
            .setFieldNamingPolicy(FieldNamingPolicy.LOWER_CASE_WITH_UNDERSCORES)
            .create()
        api = Retrofit.Builder()
            .baseUrl(server.url("api/v1/"))
            .addConverterFactory(GsonConverterFactory.create(gson))
            .build()
            .create(RemindRxApiService::class.java)
    }

    @After
    fun tearDown() {
        server.shutdown()
    }

    @Test
    fun `adherence summary and logs send date range and pagination queries`() = runBlocking {
        enqueueSuccess(
            """
            {
              "patient_id": "patient-1",
              "from_date": "2026-08-10",
              "to_date": "2026-08-14",
              "adherence_rate": 87.5,
              "total_doses": 8,
              "taken_doses": 7,
              "skipped_doses": 1,
              "missed_doses": 0
            }
            """.trimIndent(),
        )

        val summary = api.getAdherenceSummary(
            patientId = "patient-1",
            from = "2026-08-10",
            to = "2026-08-14",
        ).data

        val summaryRequest = server.takeRequest()
        assertEquals("GET", summaryRequest.method)
        assertEquals("/api/v1/patients/patient-1/adherence", summaryRequest.requestUrl?.encodedPath)
        assertEquals("2026-08-10", summaryRequest.requestUrl?.queryParameter("from"))
        assertEquals("2026-08-14", summaryRequest.requestUrl?.queryParameter("to"))
        assertEquals(87.5f, summary?.adherenceRate)

        enqueueSuccess(
            """
            {
              "content": [],
              "page_no": 2,
              "page_size": 20,
              "total_elements": 21,
              "total_pages": 2,
              "last": true
            }
            """.trimIndent(),
        )

        val logs = api.getAdherenceLogs(
            patientId = "patient-1",
            from = "2026-08-10",
            to = "2026-08-14",
            page = 2,
            size = 20,
        ).data

        val logsRequest = server.takeRequest()
        assertEquals("GET", logsRequest.method)
        assertEquals("/api/v1/patients/patient-1/adherence/logs", logsRequest.requestUrl?.encodedPath)
        assertEquals("2026-08-10", logsRequest.requestUrl?.queryParameter("from"))
        assertEquals("2026-08-14", logsRequest.requestUrl?.queryParameter("to"))
        assertEquals("2", logsRequest.requestUrl?.queryParameter("page"))
        assertEquals("20", logsRequest.requestUrl?.queryParameter("size"))
        assertEquals(2, logs?.pageNo)
        assertTrue(logs?.last == true)
    }

    @Test
    fun `routine update uses PUT path and snake case JSON`() = runBlocking {
        enqueueSuccess(
            """
            {
              "id": "routine-1",
              "patient_id": "patient-1",
              "wake_time": "06:30:00",
              "breakfast_time": "07:00:00",
              "lunch_time": "11:30:00",
              "dinner_time": "18:00:00",
              "sleep_time": "22:00:00",
              "updated_at": "2026-08-14T00:00:00Z"
            }
            """.trimIndent(),
        )

        api.updateRoutine(
            patientId = "patient-1",
            request = UpdateRoutineRequestDto(
                wakeTime = "06:30",
                breakfastTime = "07:00",
                lunchTime = "11:30",
                dinnerTime = "18:00",
                sleepTime = "22:00",
            ),
        )

        val request = server.takeRequest()
        val body = JsonParser.parseString(request.body.readUtf8()).asJsonObject
        assertEquals("PUT", request.method)
        assertEquals("/api/v1/patients/patient-1/routine", request.requestUrl?.encodedPath)
        assertEquals("06:30", body["wake_time"].asString)
        assertEquals("07:00", body["breakfast_time"].asString)
        assertEquals("11:30", body["lunch_time"].asString)
        assertEquals("18:00", body["dinner_time"].asString)
        assertEquals("22:00", body["sleep_time"].asString)
        assertFalse(body.has("wakeTime"))
    }

    @Test
    fun `reschedule uses POST path and reason body`() = runBlocking {
        enqueueSuccess(
            """
            {
              "agent_run_id": "run-1",
              "status": "RUNNING",
              "message": "Reschedule started"
            }
            """.trimIndent(),
            statusCode = 202,
        )

        val result = api.reschedule(
            patientId = "patient-1",
            request = RescheduleRequestDto(reason = "Routine updated"),
        ).data

        val request = server.takeRequest()
        val body = JsonParser.parseString(request.body.readUtf8()).asJsonObject
        assertEquals("POST", request.method)
        assertEquals(
            "/api/v1/patients/patient-1/schedules/reschedule",
            request.requestUrl?.encodedPath,
        )
        assertEquals("Routine updated", body["reason"].asString)
        assertEquals("run-1", result?.agentRunId)
    }

    @Test
    fun `caregiver CRUD uses patient scoped paths and snake case create body`() = runBlocking {
        enqueueSuccess("[]")

        api.getCaregivers("patient-1")

        val listRequest = server.takeRequest()
        assertEquals("GET", listRequest.method)
        assertEquals(
            "/api/v1/patients/patient-1/caregivers",
            listRequest.requestUrl?.encodedPath,
        )

        enqueueSuccess(
            """
            {
              "id": "link-1",
              "patient_id": "patient-1",
              "caregiver_user_id": "caregiver-1",
              "relationship": "Con gái",
              "channels": ["APP_NOTIFICATION"],
              "status": "ACTIVE",
              "created_at": "2026-08-14T00:00:00Z",
              "temp_password": "123456"
            }
            """.trimIndent(),
            statusCode = 201,
        )

        val created = api.createCaregiver(
            patientId = "patient-1",
            request = CreateCaregiverLinkRequestDto(
                caregiverPhone = "+84901234567",
                relationship = "Con gái",
            ),
        ).data

        val createRequest = server.takeRequest()
        val createBody = JsonParser.parseString(createRequest.body.readUtf8()).asJsonObject
        assertEquals("POST", createRequest.method)
        assertEquals(
            "/api/v1/patients/patient-1/caregivers",
            createRequest.requestUrl?.encodedPath,
        )
        assertEquals("+84901234567", createBody["caregiver_phone"].asString)
        assertEquals("Con gái", createBody["relationship"].asString)
        assertEquals("APP_NOTIFICATION", createBody["channels"].asJsonArray[0].asString)
        assertFalse(createBody.has("caregiverPhone"))
        assertEquals("caregiver-1", created?.caregiverUserId)

        enqueueSuccess("""{"message":"Caregiver link removed successfully"}""")

        api.deleteCaregiver(patientId = "patient-1", caregiverLinkId = "link-1")

        val deleteRequest = server.takeRequest()
        assertEquals("DELETE", deleteRequest.method)
        assertEquals(
            "/api/v1/patients/patient-1/caregivers/link-1",
            deleteRequest.requestUrl?.encodedPath,
        )
    }

    @Test
    fun `medication detail uses catalog path and parses snake case fields`() = runBlocking {
        enqueueSuccess(
            """
            {
              "id": "medication-1",
              "name": "Paracetamol",
              "composition": "Paracetamol 500mg",
              "manufacturer": "Example Pharma",
              "uses": "Giảm đau, hạ sốt",
              "side_effects": "Buồn nôn",
              "image_url": "https://example.test/paracetamol.png",
              "source_name": "Drug catalog",
              "is_active": true
            }
            """.trimIndent(),
        )

        val medication = api.getMedicationDetail("medication-1").data

        val request = server.takeRequest()
        assertEquals("GET", request.method)
        assertEquals("/api/v1/medications/medication-1", request.requestUrl?.encodedPath)
        assertEquals("Buồn nôn", medication?.sideEffects)
        assertEquals("Drug catalog", medication?.sourceName)
        assertTrue(medication?.isActive == true)
    }

    private fun enqueueSuccess(data: String, statusCode: Int = 200) {
        server.enqueue(
            MockResponse()
                .setResponseCode(statusCode)
                .setHeader("Content-Type", "application/json")
                .setBody(
                    """
                    {
                      "success": true,
                      "code": $statusCode,
                      "message": "ok",
                      "data": $data,
                      "errors": null
                    }
                    """.trimIndent(),
                ),
        )
    }
}
