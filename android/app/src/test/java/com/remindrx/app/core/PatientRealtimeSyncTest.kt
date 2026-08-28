package com.remindrx.app.core

import android.app.Application
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleOwner
import androidx.lifecycle.LifecycleRegistry
import com.remindrx.app.data.repository.AuthSession
import com.remindrx.app.data.repository.SessionPersistence
import com.remindrx.app.data.repository.SessionStore
import java.util.concurrent.CopyOnWriteArrayList
import java.util.concurrent.TimeUnit
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.launch
import okhttp3.OkHttpClient
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.json.JSONObject
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

/**
 * PatientRealtimeSync registers with ProcessLifecycleOwner in its init block, which needs a
 * real (or shadowed) Android Looper/manifest-provider environment to construct at all — hence
 * Robolectric instead of a plain JVM unit test. The Hilt-wired Application is bypassed
 * (`application = Application::class`) since this test drives the class directly and never
 * touches the DI graph.
 */
@RunWith(RobolectricTestRunner::class)
@Config(application = Application::class)
class PatientRealtimeSyncTest {
    private lateinit var server: MockWebServer
    private lateinit var client: OkHttpClient
    private lateinit var sessionStore: SessionStore
    private lateinit var sync: PatientRealtimeSync
    private lateinit var owner: FakeLifecycleOwner
    private val collectorScope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private var collectorJob: Job? = null

    private val session = AuthSession(
        accessToken = "access-token",
        refreshToken = "refresh-token",
        patientId = "patient-1",
        isFirstLogin = false,
        phone = "0900000000",
    )

    @Before
    fun setUp() {
        server = MockWebServer()
        server.start()
        client = OkHttpClient()
        sessionStore = SessionStore(FixedSessionPersistence(session))
        sync = PatientRealtimeSync(client, sessionStore, server.url("/api/v1/"))
        owner = FakeLifecycleOwner()
    }

    @After
    fun tearDown() {
        collectorJob?.cancel()
        collectorScope.cancel()
        // Release the client's own sockets/threads first — otherwise a WebSocket left open by
        // a test (e.g. after onStop's close handshake) can make MockWebServer.shutdown() hang.
        client.dispatcher.executorService.shutdown()
        client.connectionPool.evictAll()
        server.shutdown()
    }

    @Test
    fun `foregrounding connects and emits both realtime events once the socket opens`() {
        val events = collectEvents()

        server.enqueue(MockResponse().withWebSocketUpgrade(AcceptingServerListener()))
        sync.onStart(owner)

        val request = server.takeRequest(5, TimeUnit.SECONDS)
        assertTrue("expected a /ws/patient connection attempt", request != null)
        assertTrue(request!!.path!!.startsWith("/ws/patient"))
        assertTrue(request.path!!.contains("token=access-token"))

        awaitEvents(events, count = 2, timeoutMs = 3_000)
        assertEquals(
            listOf(PatientRealtimeEventType.ROUTINE_UPDATED, PatientRealtimeEventType.SCHEDULE_UPDATED),
            events.map { it.type },
        )
    }

    @Test
    fun `a routine-updated frame for this patient emits ROUTINE_UPDATED only`() {
        val events = collectEvents()
        val serverSocket = CopyOnWriteArrayList<WebSocket>()
        server.enqueue(
            MockResponse().withWebSocketUpgrade(
                AcceptingServerListener(onOpen = { ws -> serverSocket.add(ws) }),
            ),
        )
        sync.onStart(owner)
        server.takeRequest(5, TimeUnit.SECONDS)
        awaitEvents(events, count = 2, timeoutMs = 3_000) // the onOpen ROUTINE/SCHEDULE pair
        events.clear()

        val frame = JSONObject().apply {
            put("event_type", "routine.updated")
            put("data", JSONObject().apply { put("patient_id", "patient-1") })
        }
        awaitCondition(timeoutMs = 3_000) { serverSocket.isNotEmpty() }
        serverSocket.first().send(frame.toString())

        awaitEvents(events, count = 1, timeoutMs = 3_000)
        assertEquals(listOf(PatientRealtimeEventType.ROUTINE_UPDATED), events.map { it.type })
    }

    @Test
    fun `a frame for a different patient is ignored`() {
        val events = collectEvents()
        val serverSocket = CopyOnWriteArrayList<WebSocket>()
        server.enqueue(
            MockResponse().withWebSocketUpgrade(
                AcceptingServerListener(onOpen = { ws -> serverSocket.add(ws) }),
            ),
        )
        sync.onStart(owner)
        server.takeRequest(5, TimeUnit.SECONDS)
        awaitEvents(events, count = 2, timeoutMs = 3_000)
        events.clear()

        val frame = JSONObject().apply {
            put("event_type", "schedule.updated")
            put("data", JSONObject().apply { put("patient_id", "some-other-patient") })
        }
        awaitCondition(timeoutMs = 3_000) { serverSocket.isNotEmpty() }
        serverSocket.first().send(frame.toString())

        Thread.sleep(500)
        assertTrue("cross-patient frame must not surface as a realtime event", events.isEmpty())
    }

    @Test
    fun `backgrounding closes the socket and does not reconnect`() {
        server.enqueue(MockResponse().withWebSocketUpgrade(AcceptingServerListener()))
        sync.onStart(owner)
        assertTrue(server.takeRequest(5, TimeUnit.SECONDS) != null)

        sync.onStop(owner)

        // Give the (never-scheduled) reconnect a generous window to prove it does not happen.
        val secondRequest = server.takeRequest(3, TimeUnit.SECONDS)
        assertNull("backgrounded sync must not reconnect", secondRequest)
    }

    @Test
    fun `a server-initiated close while foregrounded triggers a reconnect`() {
        server.enqueue(MockResponse().withWebSocketUpgrade(ClosingServerListener()))
        server.enqueue(MockResponse().withWebSocketUpgrade(AcceptingServerListener()))

        sync.onStart(owner)
        val first = server.takeRequest(5, TimeUnit.SECONDS)
        assertTrue(first != null)

        // PatientRealtimeSync waits ~2s before reconnecting; give it headroom.
        val second = server.takeRequest(6, TimeUnit.SECONDS)
        assertTrue("expected an automatic reconnect after the server closed the socket", second != null)
    }

    private fun collectEvents(): CopyOnWriteArrayList<PatientRealtimeEvent> {
        val events = CopyOnWriteArrayList<PatientRealtimeEvent>()
        collectorJob = collectorScope.launch {
            sync.events.collect { events.add(it) }
        }
        // Let the collector coroutine actually subscribe before the caller triggers emissions.
        Thread.sleep(50)
        return events
    }

    private fun awaitEvents(events: List<*>, count: Int, timeoutMs: Long) {
        awaitCondition(timeoutMs) { events.size >= count }
    }

    private fun awaitCondition(timeoutMs: Long, condition: () -> Boolean) {
        val deadline = System.currentTimeMillis() + timeoutMs
        while (System.currentTimeMillis() < deadline) {
            if (condition()) return
            Thread.sleep(25)
        }
        assertTrue("condition not met within ${timeoutMs}ms", condition())
    }
}

private class FixedSessionPersistence(private val session: AuthSession?) : SessionPersistence {
    override fun read(): AuthSession? = session
    override fun write(session: AuthSession) = Unit
    override fun clear() = Unit
}

private class FakeLifecycleOwner : LifecycleOwner {
    private val registry = LifecycleRegistry(this).apply { currentState = Lifecycle.State.STARTED }
    override val lifecycle: Lifecycle get() = registry
}

/** Accepts the WS upgrade and does nothing else unless [onOpen] is supplied. */
private class AcceptingServerListener(
    private val onOpen: (WebSocket) -> Unit = {},
) : WebSocketListener() {
    override fun onOpen(webSocket: WebSocket, response: okhttp3.Response) {
        onOpen.invoke(webSocket)
    }

    // Reciprocate a client-initiated close (e.g. PatientRealtimeSync.onStop) so the handshake
    // completes and MockWebServer.shutdown() doesn't hang waiting on a half-closed socket.
    override fun onClosing(webSocket: WebSocket, code: Int, reason: String) {
        webSocket.close(code, reason)
    }
}

/** Accepts the WS upgrade, then immediately closes it — used to exercise reconnect. */
private class ClosingServerListener : WebSocketListener() {
    override fun onOpen(webSocket: WebSocket, response: okhttp3.Response) {
        webSocket.close(1000, "server closing")
    }
}
