package com.dosely.app.core

import androidx.lifecycle.DefaultLifecycleObserver
import androidx.lifecycle.LifecycleOwner
import androidx.lifecycle.ProcessLifecycleOwner
import com.dosely.app.data.repository.AuthRepository
import com.dosely.app.data.repository.AuthSession
import com.dosely.app.data.repository.SessionStore
import javax.inject.Inject
import javax.inject.Qualifier
import javax.inject.Singleton
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.asSharedFlow
import kotlinx.coroutines.flow.collectLatest
import kotlinx.coroutines.launch
import okhttp3.HttpUrl
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import org.json.JSONObject

/** Origin (scheme/host/port) resolved to `ApiConfig.BASE_URL` in production; overridable in tests. */
@Qualifier
@Retention(AnnotationRetention.BINARY)
annotation class PatientRealtimeBaseUrl

enum class PatientRealtimeEventType { ROUTINE_UPDATED, SCHEDULE_UPDATED }

data class PatientRealtimeEvent(val type: PatientRealtimeEventType)

interface PatientRealtimeEvents {
    val events: SharedFlow<PatientRealtimeEvent>
}

object NoopPatientRealtimeEvents : PatientRealtimeEvents {
    override val events: SharedFlow<PatientRealtimeEvent> =
        MutableSharedFlow<PatientRealtimeEvent>(0).asSharedFlow()
}

/**
 * Foreground-only connection to the patient-specific realtime feed.
 *
 * Protocol (Area 4a): the token is never put in the URL. After the socket opens
 * the client sends `{"type":"auth","token":"<access>"}` and treats the socket as
 * live only once `{"type":"auth_ok","expires_in":N}` arrives. Before the access
 * token expires it refreshes the session and re-sends an auth frame on the open
 * socket. Close 4401 (unauthenticated/expired) refreshes the session and
 * reconnects; 4403 (wrong role) stops for good; anything else reconnects with
 * exponential backoff.
 *
 * The server filters frames to the access-token subject.  Frames carry no
 * health data; the ViewModel reloads its authenticated REST resource after a
 * signal, keeping the server as the source of truth and avoiding local merge
 * rules for clinical-adjacent scheduling data.
 */
@Singleton
class PatientRealtimeSync @Inject constructor(
    private val client: OkHttpClient,
    private val sessionStore: SessionStore,
    @PatientRealtimeBaseUrl private val apiBaseUrl: HttpUrl,
    private val authRepository: AuthRepository,
) : DefaultLifecycleObserver, PatientRealtimeEvents {
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private val mutableEvents = MutableSharedFlow<PatientRealtimeEvent>(extraBufferCapacity = 8)
    override val events: SharedFlow<PatientRealtimeEvent> = mutableEvents.asSharedFlow()

    /** First reconnect delay; doubles per consecutive failure up to [MAX_RECONNECT_DELAY_MS]. Tests shrink it. */
    internal var reconnectBaseDelayMs: Long = DEFAULT_RECONNECT_DELAY_MS

    private val lock = Any()
    private var isForeground = false
    private var socket: WebSocket? = null
    private var reconnectJob: Job? = null
    private var reauthJob: Job? = null
    private var attempt = 0
    private var blocked = false
    private var observedSession: AuthSession? = sessionStore.session.value

    init {
        ProcessLifecycleOwner.get().lifecycle.addObserver(this)
        scope.launch {
            sessionStore.session.collectLatest { session ->
                val previous: AuthSession?
                synchronized(lock) {
                    previous = observedSession
                    observedSession = session
                }
                if (session?.patientId != previous?.patientId) {
                    synchronized(lock) { blocked = false; attempt = 0 }
                    if (isForeground) connect()
                }
                // Same patient with rotated tokens: keep the socket, it re-authenticates in band.
            }
        }
    }

    override fun onStart(owner: LifecycleOwner) {
        synchronized(lock) {
            isForeground = true
            attempt = 0
        }
        connect()
    }

    override fun onStop(owner: LifecycleOwner) {
        synchronized(lock) {
            isForeground = false
            reconnectJob?.cancel()
            reconnectJob = null
            reauthJob?.cancel()
            reauthJob = null
            socket?.close(NORMAL_CLOSURE, "App backgrounded")
            socket = null
        }
    }

    private fun connect() {
        synchronized(lock) {
            reconnectJob?.cancel()
            reconnectJob = null
            reauthJob?.cancel()
            reauthJob = null
            socket?.cancel()
            socket = null
            val session = observedSession
            if (!isForeground || session == null || blocked) return

            // OkHttp's WebSocket upgrade runs over a plain http(s) request — HttpUrl.Builder.scheme()
            // only accepts "http"/"https" and throws for "ws"/"wss", so the URL keeps apiBaseUrl's
            // own scheme unchanged. No token in the URL: it is sent in the first message.
            val wsUrl = apiBaseUrl.newBuilder()
                .encodedPath("/ws/patient")
                .query(null)
                .build()
            socket = client.newWebSocket(
                Request.Builder().url(wsUrl).build(),
                Listener(session.patientId),
            )
        }
    }

    private fun scheduleReconnect() {
        synchronized(lock) {
            if (!isForeground || blocked || reconnectJob?.isActive == true) return
            val delayMs = (reconnectBaseDelayMs shl attempt.coerceAtMost(MAX_BACKOFF_SHIFT))
                .coerceAtMost(MAX_RECONNECT_DELAY_MS)
            attempt += 1
            reconnectJob = scope.launch {
                delay(delayMs)
                synchronized(lock) { reconnectJob = null }
                connect()
            }
        }
    }

    /** 4401: the access token was missing/expired. Refresh the session, then reconnect with backoff. */
    private fun refreshThenReconnect() {
        scope.launch {
            runCatching { authRepository.refreshSession() }
            // A rejected refresh clears the session; connect() then no-ops because there is none.
            scheduleReconnect()
        }
    }

    private fun scheduleReauth(webSocket: WebSocket, expiresInSeconds: Long) {
        synchronized(lock) {
            reauthJob?.cancel()
            val waitSeconds = (expiresInSeconds - REAUTH_MARGIN_SECONDS).coerceAtLeast(MIN_REAUTH_SECONDS)
            reauthJob = scope.launch {
                delay(waitSeconds * 1_000L)
                val renewed = runCatching { authRepository.refreshSession() }.getOrNull()
                val stillCurrent = synchronized(lock) { socket === webSocket }
                if (!stillCurrent) return@launch
                if (renewed != null) {
                    webSocket.send(authFrame(renewed.accessToken))
                } else {
                    // Could not renew: drop the socket; the close path reconnects with backoff.
                    webSocket.close(NORMAL_CLOSURE, "re-auth failed")
                }
            }
        }
    }

    private fun handleClosed(webSocket: WebSocket, code: Int) {
        synchronized(lock) {
            if (socket !== webSocket) return
            socket = null
            reauthJob?.cancel()
            reauthJob = null
        }
        when (code) {
            CLOSE_FORBIDDEN -> synchronized(lock) { blocked = true }
            CLOSE_UNAUTHENTICATED -> refreshThenReconnect()
            else -> scheduleReconnect()
        }
    }

    private fun authFrame(token: String): String =
        JSONObject().put("type", "auth").put("token", token).toString()

    private inner class Listener(private val patientId: String) : WebSocketListener() {
        private var authenticated = false

        override fun onOpen(webSocket: WebSocket, response: Response) {
            val token = sessionStore.accessToken
            if (token == null) {
                webSocket.close(NORMAL_CLOSURE, "no session")
                return
            }
            webSocket.send(authFrame(token))
        }

        override fun onMessage(webSocket: WebSocket, text: String) {
            val json = runCatching { JSONObject(text) }.getOrNull() ?: return

            // Control frames carry `type`; events carry `event_type`. Unknown types are ignored.
            val type = json.optString("type")
            if (type.isNotEmpty()) {
                if (type == "auth_ok") {
                    authenticated = true
                    synchronized(lock) { attempt = 0 }
                    scheduleReauth(webSocket, json.optLong("expires_in", 0L))
                    // WebSocket carries no replay. Reload both server resources after every
                    // authenticated connection so a change made while backgrounded is
                    // observed without waiting for another event.
                    mutableEvents.tryEmit(PatientRealtimeEvent(PatientRealtimeEventType.ROUTINE_UPDATED))
                    mutableEvents.tryEmit(PatientRealtimeEvent(PatientRealtimeEventType.SCHEDULE_UPDATED))
                }
                return
            }
            if (!authenticated) return

            val framePatientId = json.optJSONObject("data")?.optString("patient_id") ?: return
            if (framePatientId != patientId) return
            when (json.optString("event_type")) {
                "routine.updated" -> mutableEvents.tryEmit(PatientRealtimeEvent(PatientRealtimeEventType.ROUTINE_UPDATED))
                "schedule.updated" -> mutableEvents.tryEmit(PatientRealtimeEvent(PatientRealtimeEventType.SCHEDULE_UPDATED))
            }
        }

        override fun onClosing(webSocket: WebSocket, code: Int, reason: String) {
            // OkHttp only finalizes the close handshake (and later calls onClosed) once the
            // client reciprocates; without this, a server-initiated close never completes and
            // the reconnect would only run after a much later read-timeout failure, if ever.
            // Reserved codes (1005/1006/1015) cannot be sent back; fall back to a normal close.
            runCatching { webSocket.close(code, reason) }
                .onFailure { webSocket.close(NORMAL_CLOSURE, null) }
            handleClosed(webSocket, code)
        }

        override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
            handleClosed(webSocket, ABNORMAL_CLOSURE)
        }

        override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {
            handleClosed(webSocket, code)
        }
    }

    private companion object {
        const val NORMAL_CLOSURE = 1000
        const val ABNORMAL_CLOSURE = 1006
        const val CLOSE_UNAUTHENTICATED = 4401
        const val CLOSE_FORBIDDEN = 4403
        const val DEFAULT_RECONNECT_DELAY_MS = 1_000L
        const val MAX_RECONNECT_DELAY_MS = 30_000L
        const val MAX_BACKOFF_SHIFT = 5
        const val REAUTH_MARGIN_SECONDS = 60L
        const val MIN_REAUTH_SECONDS = 5L
    }
}
