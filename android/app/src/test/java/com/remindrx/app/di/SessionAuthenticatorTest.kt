package com.remindrx.app.di

import com.remindrx.app.data.remote.AuthTokenResponseDto
import com.remindrx.app.data.remote.UserDto
import com.remindrx.app.data.repository.FakeSessionPersistence
import com.remindrx.app.data.repository.SessionStore
import com.remindrx.app.data.repository.testSession
import java.util.concurrent.CountDownLatch
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicInteger
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test

class SessionAuthenticatorTest {
    private lateinit var server: MockWebServer

    @Before
    fun setUp() {
        server = MockWebServer()
        server.start()
    }

    @After
    fun tearDown() {
        server.shutdown()
    }

    @Test
    fun `401 refreshes once and replays request with rotated access token`() {
        server.enqueue(MockResponse().setResponseCode(401))
        server.enqueue(MockResponse().setResponseCode(200).setBody("ok"))
        val store = SessionStore(FakeSessionPersistence(testSession()))
        val refreshCalls = AtomicInteger()
        val client = authenticatedClient(store) {
            refreshCalls.incrementAndGet()
            refreshedTokens()
        }

        client.newCall(Request.Builder().url(server.url("api/v1/patients/patient-1/routine")).build())
            .execute()
            .use { assertEquals(200, it.code) }

        assertEquals(1, refreshCalls.get())
        assertEquals("Bearer access-old", server.takeRequest().getHeader("Authorization"))
        assertEquals("Bearer access-new", server.takeRequest().getHeader("Authorization"))
        assertEquals("access-new", store.accessToken)
        assertEquals("refresh-new", store.refreshToken)
    }

    @Test
    fun `second 401 is returned without a second refresh attempt`() {
        server.enqueue(MockResponse().setResponseCode(401))
        server.enqueue(MockResponse().setResponseCode(401))
        val store = SessionStore(FakeSessionPersistence(testSession()))
        val refreshCalls = AtomicInteger()
        val client = authenticatedClient(store) {
            refreshCalls.incrementAndGet()
            refreshedTokens()
        }

        client.newCall(Request.Builder().url(server.url("api/v1/patients/patient-1/routine")).build())
            .execute()
            .use { assertEquals(401, it.code) }

        assertEquals(1, refreshCalls.get())
        assertEquals(2, server.requestCount)
    }

    @Test
    fun `failed refresh clears session and does not replay request`() {
        server.enqueue(MockResponse().setResponseCode(401))
        val store = SessionStore(FakeSessionPersistence(testSession()))
        val client = authenticatedClient(store) { null }

        client.newCall(Request.Builder().url(server.url("api/v1/patients/patient-1/routine")).build())
            .execute()
            .use { assertEquals(401, it.code) }

        assertNull(store.session.value)
        assertEquals(1, server.requestCount)
    }

    @Test
    fun `login is never decorated or refreshed`() {
        server.enqueue(MockResponse().setResponseCode(401))
        val store = SessionStore(FakeSessionPersistence(testSession()))
        val refreshCalls = AtomicInteger()
        val client = authenticatedClient(store) {
            refreshCalls.incrementAndGet()
            refreshedTokens()
        }

        client.newCall(Request.Builder().url(server.url("api/v1/auth/login")).build())
            .execute()
            .use { assertEquals(401, it.code) }

        assertNull(server.takeRequest().getHeader("Authorization"))
        assertEquals(0, refreshCalls.get())
    }

    @Test
    fun `logout during refresh prevents stale response from repopulating session`() {
        server.enqueue(MockResponse().setResponseCode(401))
        val original = testSession()
        val store = SessionStore(FakeSessionPersistence(original))
        val refreshStarted = CountDownLatch(1)
        val finishRefresh = CountDownLatch(1)
        val client = authenticatedClient(store) { refreshToken ->
            assertEquals(original.refreshToken, refreshToken)
            refreshStarted.countDown()
            assertTrue(finishRefresh.await(5, TimeUnit.SECONDS))
            refreshedTokens()
        }
        val executor = Executors.newSingleThreadExecutor()

        try {
            val responseCode = executor.submit<Int> { executeProtectedRequest(client) }
            assertTrue(refreshStarted.await(5, TimeUnit.SECONDS))

            store.clear()
            finishRefresh.countDown()

            assertEquals(401, responseCode.get(5, TimeUnit.SECONDS))
            assertNull(store.session.value)
            assertEquals(1, server.requestCount)
        } finally {
            finishRefresh.countDown()
            executor.shutdownNow()
        }
    }

    @Test
    fun `new login during refresh is not overwritten by stale success`() {
        server.enqueue(MockResponse().setResponseCode(401))
        val store = SessionStore(FakeSessionPersistence(testSession()))
        val replacement = testSession(
            accessToken = "access-login-b",
            refreshToken = "refresh-login-b",
            patientId = "patient-2",
            phone = "+84909999999",
        )
        val refreshStarted = CountDownLatch(1)
        val finishRefresh = CountDownLatch(1)
        val client = authenticatedClient(store) {
            refreshStarted.countDown()
            assertTrue(finishRefresh.await(5, TimeUnit.SECONDS))
            refreshedTokens()
        }
        val executor = Executors.newSingleThreadExecutor()

        try {
            val responseCode = executor.submit<Int> { executeProtectedRequest(client) }
            assertTrue(refreshStarted.await(5, TimeUnit.SECONDS))

            store.update(replacement)
            finishRefresh.countDown()

            assertEquals(401, responseCode.get(5, TimeUnit.SECONDS))
            assertEquals(replacement, store.session.value)
            assertEquals(1, server.requestCount)
        } finally {
            finishRefresh.countDown()
            executor.shutdownNow()
        }
    }

    @Test
    fun `new login during failed refresh is not cleared`() {
        server.enqueue(MockResponse().setResponseCode(401))
        val store = SessionStore(FakeSessionPersistence(testSession()))
        val replacement = testSession(
            accessToken = "access-login-b",
            refreshToken = "refresh-login-b",
            patientId = "patient-2",
            phone = "+84909999999",
        )
        val refreshStarted = CountDownLatch(1)
        val finishRefresh = CountDownLatch(1)
        val client = authenticatedClient(store) {
            refreshStarted.countDown()
            assertTrue(finishRefresh.await(5, TimeUnit.SECONDS))
            null
        }
        val executor = Executors.newSingleThreadExecutor()

        try {
            val responseCode = executor.submit<Int> { executeProtectedRequest(client) }
            assertTrue(refreshStarted.await(5, TimeUnit.SECONDS))

            store.update(replacement)
            finishRefresh.countDown()

            assertEquals(401, responseCode.get(5, TimeUnit.SECONDS))
            assertEquals(replacement, store.session.value)
            assertEquals(1, server.requestCount)
        } finally {
            finishRefresh.countDown()
            executor.shutdownNow()
        }
    }

    private fun authenticatedClient(
        store: SessionStore,
        refresh: TokenRefreshGateway,
    ): OkHttpClient = OkHttpClient.Builder()
        .addInterceptor(BearerTokenInterceptor(store))
        .authenticator(SessionAuthenticator(store, refresh))
        .build()

    private fun executeProtectedRequest(client: OkHttpClient): Int = client.newCall(
        Request.Builder().url(server.url("api/v1/patients/patient-1/routine")).build(),
    ).execute().use { it.code }

    private fun refreshedTokens() = AuthTokenResponseDto(
        accessToken = "access-new",
        refreshToken = "refresh-new",
        tokenType = "Bearer",
        expiresIn = 900,
        mustChangePassword = false,
        needOnboarding = false,
        user = UserDto(
            id = "patient-1",
            phone = "+84901234567",
            role = "PATIENT",
            status = "ACTIVE",
        ),
    )
}
