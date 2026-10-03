package com.dosely.app.data.repository

import com.google.gson.FieldNamingPolicy
import com.google.gson.GsonBuilder
import com.dosely.app.data.remote.DoselyApiService
import kotlinx.coroutines.runBlocking
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Before
import org.junit.Test
import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory

class RemoteAuthRepositoryImplTest {
    private lateinit var server: MockWebServer
    private lateinit var store: SessionStore
    private lateinit var repository: RemoteAuthRepositoryImpl

    @Before
    fun setUp() {
        server = MockWebServer()
        server.start()
        val gson = GsonBuilder()
            .setFieldNamingPolicy(FieldNamingPolicy.LOWER_CASE_WITH_UNDERSCORES)
            .create()
        val api = Retrofit.Builder()
            .baseUrl(server.url("api/v1/"))
            .addConverterFactory(GsonConverterFactory.create(gson))
            .build()
            .create(DoselyApiService::class.java)
        store = SessionStore(FakeSessionPersistence())
        repository = RemoteAuthRepositoryImpl(api, store)
    }

    @After
    fun tearDown() {
        server.shutdown()
    }

    @Test
    fun `login persists complete token pair and patient identity`() = runBlocking {
        server.enqueue(successTokenResponse("access-1", "refresh-1", true))

        val session = repository.login("0901234567", "123456")

        assertEquals(session, store.session.value)
        assertEquals("access-1", session.accessToken)
        assertEquals("refresh-1", session.refreshToken)
        assertEquals("patient-1", session.patientId)
        assertEquals("+84901234567", session.phone)
        assertEquals("/api/v1/auth/login", server.takeRequest().path)
    }

    @Test
    fun `manual refresh rotates persisted token pair`() = runBlocking {
        store.update(testSession())
        server.enqueue(successTokenResponse("access-2", "refresh-2", false))

        val refreshed = repository.refreshSession()

        assertEquals("access-2", refreshed.accessToken)
        assertEquals("refresh-2", store.refreshToken)
        val request = server.takeRequest()
        assertEquals("/api/v1/auth/refresh", request.path)
        assertEquals(true, request.body.readUtf8().contains("refresh-old"))
    }

    @Test
    fun `refresh rejection clears local session`() = runBlocking {
        store.update(testSession())
        server.enqueue(MockResponse().setResponseCode(401).setBody(ERROR_RESPONSE))

        runCatching { repository.refreshSession() }

        assertNull(store.session.value)
    }

    @Test
    fun `change pin obtains a fresh renewable session`() = runBlocking {
        store.update(testSession())
        server.enqueue(successWithoutData())
        server.enqueue(successTokenResponse("access-after-pin", "refresh-after-pin", false))

        repository.changePin("access-old", "123456", "654321")

        assertEquals("access-after-pin", store.accessToken)
        assertEquals("refresh-after-pin", store.refreshToken)
        assertEquals(false, store.mustChangePassword)
        assertEquals(false, store.needOnboarding)
        val changeRequest = server.takeRequest()
        assertEquals("Bearer access-old", changeRequest.getHeader("Authorization"))
        assertEquals("/api/v1/auth/login", server.takeRequest().path)
    }

    @Test
    fun `logout revokes refresh token and always clears local session`() = runBlocking {
        store.update(testSession())
        server.enqueue(successWithoutData())

        repository.logout()

        assertNull(store.session.value)
        val request = server.takeRequest()
        assertEquals("/api/v1/auth/logout", request.path)
        assertEquals(true, request.body.readUtf8().contains("refresh-old"))
    }

    private fun successTokenResponse(
        accessToken: String,
        refreshToken: String,
        mustChangePassword: Boolean,
        needOnboarding: Boolean = false,
    ): MockResponse = MockResponse()
        .setResponseCode(200)
        .setHeader("Content-Type", "application/json")
        .setBody(
            """
            {
              "success": true,
              "code": 200,
              "message": "ok",
              "data": {
                "access_token": "$accessToken",
                "refresh_token": "$refreshToken",
                "token_type": "Bearer",
                "expires_in": 900,
                "must_change_password": $mustChangePassword,
                "need_onboarding": $needOnboarding,
                "user": {
                  "id": "patient-1",
                  "phone": "+84901234567",
                  "role": "PATIENT",
                  "status": "ACTIVE"
                }
              },
              "errors": null
            }
            """.trimIndent(),
        )

    private fun successWithoutData(): MockResponse = MockResponse()
        .setResponseCode(200)
        .setHeader("Content-Type", "application/json")
        .setBody(
            """
            {"success":true,"code":200,"message":"ok","data":null,"errors":null}
            """.trimIndent(),
        )

    private companion object {
        const val ERROR_RESPONSE =
            "{\"success\":false,\"code\":401,\"message\":\"unauthorized\",\"data\":null,\"errors\":null}"
    }
}
