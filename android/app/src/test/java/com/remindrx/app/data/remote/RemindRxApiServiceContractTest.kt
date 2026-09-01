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
    fun `app update endpoint is public and parses camel case release metadata`() = runBlocking {
        enqueueSuccess(
            """
            {
              "versionCode": 7,
              "versionName": "1.5.0",
              "downloadUrl": "https://api.example.test/downloads/remindrx-demo.apk"
            }
            """.trimIndent(),
        )

        val latest = api.getLatestAppVersion().data
        val request = server.takeRequest()

        assertEquals("GET", request.method)
        assertEquals("/api/v1/app/latest-version", request.requestUrl?.encodedPath)
        assertEquals(7, latest?.versionCode)
        assertEquals("1.5.0", latest?.versionName)
        assertEquals(
            "https://api.example.test/downloads/remindrx-demo.apk",
            latest?.downloadUrl,
        )
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

    @Test
    fun `chat endpoints unwrap the standard envelope`() = runBlocking {
        // src/modules/agents/router.py trả success_response() cho cả /chat và
        // /chat/voice, nên payload nằm trong data — đọc thẳng model trần sẽ ra null.
        enqueueSuccess("""{"response": "Liều tiếp theo lúc 20:00.", "conversationId": "conv-1"}""")

        val reply = api.sendChatMessage(
            ChatRequestDto(
                message = "Liều tiếp theo lúc mấy giờ?",
                conversationId = "conv-1",
                clientDate = "2026-08-29",
                clientDateTime = "2026-08-29T23:30:00+07:00",
            ),
        )

        val request = server.takeRequest()
        assertEquals("POST", request.method)
        assertEquals("/api/v1/chat", request.requestUrl?.encodedPath)
        val body = JsonParser.parseString(request.body.readUtf8()).asJsonObject
        assertEquals("conv-1", body.get("conversationId").asString)
        assertEquals("2026-08-29", body.get("clientDate").asString)
        assertEquals("2026-08-29T23:30:00+07:00", body.get("clientDateTime").asString)
        assertFalse(body.has("conversation_id"))
        assertTrue(reply.success)
        assertEquals("Liều tiếp theo lúc 20:00.", reply.data?.response)
        assertEquals("conv-1", reply.data?.conversationId)
    }

    @Test
    fun `chat history endpoints parse camelCase payloads`() = runBlocking {
        enqueueSuccess(
            """
            {
              "content": [
                {
                  "id": "conv-1",
                  "title": "Hỏi về thuốc",
                  "preview": "Uống sau ăn",
                  "messageCount": 2,
                  "createdAt": "2026-08-30T10:00:00Z",
                  "updatedAt": "2026-08-30T10:05:00Z"
                }
              ],
              "page_no": 1,
              "page_size": 20,
              "total_elements": 1,
              "total_pages": 1,
              "last": true
            }
            """.trimIndent(),
        )

        val list = api.getChatConversations().data
        val listRequest = server.takeRequest()
        assertEquals("/api/v1/chat/conversations", listRequest.requestUrl?.encodedPath)
        assertEquals("Hỏi về thuốc", list?.content?.first()?.title)
        assertEquals(2, list?.content?.first()?.messageCount)
        assertEquals("2026-08-30T10:05:00Z", list?.content?.first()?.updatedAt)

        enqueueSuccess(
            """
            {
              "id": "conv-1",
              "title": "Hỏi về thuốc",
              "createdAt": "2026-08-30T10:00:00Z",
              "updatedAt": "2026-08-30T10:05:00Z",
              "messages": [
                {
                  "id": "msg-1",
                  "role": "user",
                  "content": "Tôi uống thuốc lúc nào?",
                  "intent": "ASK_SCHEDULE",
                  "createdAt": "2026-08-30T10:00:00Z"
                }
              ],
              "hasMore": true,
              "nextCursor": "msg-1"
            }
            """.trimIndent(),
        )

        val detail = api.getChatConversationDetail("conv-1").data
        val detailRequest = server.takeRequest()
        assertEquals("/api/v1/chat/conversations/conv-1", detailRequest.requestUrl?.encodedPath)
        assertEquals("2026-08-30T10:05:00Z", detail?.updatedAt)
        assertEquals("2026-08-30T10:00:00Z", detail?.messages?.first()?.createdAt)
        assertTrue(detail?.hasMore == true)
        assertEquals("msg-1", detail?.nextCursor)
    }

    @Test
    fun `voice chat keeps a null audio payload when TTS fails open`() = runBlocking {
        enqueueSuccess(
            """
            {
              "transcript": "Tôi quên uống thuốc",
              "response": "Đừng uống bù gấp đôi.",
              "audio_base64": null
            }
            """.trimIndent(),
        )

        val part = okhttp3.MultipartBody.Part.createFormData(
            "audio",
            "audio.webm",
            okhttp3.RequestBody.create(null, ByteArray(0)),
        )
        val reply = api.sendVoiceChatMessage(
            part,
            okhttp3.RequestBody.create(null, "2026-08-29"),
            okhttp3.RequestBody.create(null, "2026-08-29T23:30:00+07:00"),
            okhttp3.RequestBody.create(null, "conversation-1"),
        ).data

        val request = server.takeRequest()
        assertEquals("/api/v1/chat/voice", request.requestUrl?.encodedPath)
        assertEquals("Tôi quên uống thuốc", reply?.transcript)
        assertEquals("Đừng uống bù gấp đôi.", reply?.response)
        assertEquals(null, reply?.audioBase64)
    }

    @Test
    fun `voice chat omits conversation part when starting a new conversation`() = runBlocking {
        enqueueSuccess(
            """
            {
              "transcript": "Tôi quên uống thuốc",
              "response": "Đừng uống bù gấp đôi.",
              "conversationId": "conv-new",
              "audio_base64": null
            }
            """.trimIndent(),
        )

        val part = okhttp3.MultipartBody.Part.createFormData(
            "audio",
            "audio.webm",
            okhttp3.RequestBody.create(null, ByteArray(0)),
        )
        val reply = api.sendVoiceChatMessage(
            part,
            okhttp3.RequestBody.create(null, "2026-08-29"),
            okhttp3.RequestBody.create(null, "2026-08-29T23:30:00+07:00"),
            null,
        ).data

        val request = server.takeRequest()
        assertFalse(request.body.readUtf8().contains("name=\"conversationId\""))
        assertEquals("conv-new", reply?.conversationId)
    }

    @Test
    fun `onboarding posts profile and routine to the self route`() = runBlocking {
        enqueueSuccess(
            """
            {
              "profile": {
                "user_id": "patient-1",
                "phone": "0901234567",
                "role": "PATIENT",
                "status": "ACTIVE",
                "name": "Nguyen Van B",
                "dob": "1958-04-02",
                "sex": "MALE",
                "timezone": "Asia/Ho_Chi_Minh",
                "privacy_consent_status": null,
                "emergency_note": null,
                "created_at": "2026-08-14T08:00:00Z",
                "updated_at": "2026-08-14T08:00:00Z"
              },
              "routine": {
                "id": "routine-1",
                "patient_id": "patient-1",
                "wake_time": "06:30:00",
                "breakfast_time": "07:00:00",
                "lunch_time": "11:30:00",
                "dinner_time": "18:00:00",
                "sleep_time": "22:00:00",
                "updated_at": "2026-08-14T08:00:00Z"
              }
            }
            """.trimIndent(),
        )

        val result = api.onboardPatient(
            PatientOnboardingRequestDto(
                name = "Nguyen Van B",
                dob = "1958-04-02",
                sex = "MALE",
                emergencyNote = null,
                routine = UpdateRoutineRequestDto(
                    wakeTime = "06:30",
                    breakfastTime = "07:00",
                    lunchTime = "11:30",
                    dinnerTime = "18:00",
                    sleepTime = "22:00",
                ),
            ),
        ).data

        val request = server.takeRequest()
        assertEquals("POST", request.method)
        // patient_id lấy từ token, không nằm trong path lẫn body.
        assertEquals("/api/v1/patients/me/profile", request.requestUrl?.encodedPath)

        val body = JsonParser.parseString(request.body.readUtf8()).asJsonObject
        assertFalse(body.has("patient_id"))
        assertEquals("Nguyen Van B", body.get("name").asString)
        assertEquals("06:30", body.getAsJsonObject("routine").get("wake_time").asString)
        assertEquals("Nguyen Van B", result?.profile?.name)
        assertEquals("06:30:00", result?.routine?.wakeTime)
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
