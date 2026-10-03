package com.dosely.app.core

import androidx.lifecycle.DefaultLifecycleObserver
import androidx.lifecycle.LifecycleOwner
import androidx.lifecycle.ProcessLifecycleOwner
import com.dosely.app.data.repository.AuthSession
import com.dosely.app.data.repository.SessionStore
import javax.inject.Inject
import javax.inject.Qualifier
import javax.inject.Singleton
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
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
) : DefaultLifecycleObserver, PatientRealtimeEvents {
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private val mutableEvents = MutableSharedFlow<PatientRealtimeEvent>(extraBufferCapacity = 8)
    override val events: SharedFlow<PatientRealtimeEvent> = mutableEvents.asSharedFlow()

    private var isForeground = false
    private var socket: WebSocket? = null
    private var reconnecting = false
    private var observedSession: AuthSession? = null

    init {
        ProcessLifecycleOwner.get().lifecycle.addObserver(this)
        scope.launch {
            sessionStore.session.collectLatest { session ->
                observedSession = session
                if (isForeground) connect(session)
            }
        }
    }

    override fun onStart(owner: LifecycleOwner) {
        isForeground = true
        connect(observedSession)
    }

    override fun onStop(owner: LifecycleOwner) {
        isForeground = false
        reconnecting = false
        socket?.close(NORMAL_CLOSURE, "App backgrounded")
        socket = null
    }

    private fun connect(session: AuthSession?) {
        socket?.cancel()
        socket = null
        if (!isForeground || session == null) return

        // OkHttp's WebSocket upgrade runs over a plain http(s) request — HttpUrl.Builder.scheme()
        // only accepts "http"/"https" and throws for "ws"/"wss", so the URL keeps apiBaseUrl's
        // own scheme unchanged; this used to crash every connect() call (main-thread in onStart()).
        val wsUrl = apiBaseUrl.newBuilder()
            .encodedPath("/ws/patient")
            .query(null)
            .addQueryParameter("token", session.accessToken)
            .build()
        socket = client.newWebSocket(
            Request.Builder().url(wsUrl).build(),
            Listener(session),
        )
    }

    private fun scheduleReconnect(session: AuthSession) {
        if (!isForeground || observedSession != session || reconnecting) return
        reconnecting = true
        scope.launch {
            delay(RECONNECT_DELAY_MS)
            reconnecting = false
            if (isForeground && observedSession == session) connect(session)
        }
    }

    private inner class Listener(private val session: AuthSession) : WebSocketListener() {
        override fun onOpen(webSocket: WebSocket, response: Response) {
            // WebSocket carries no replay. Reload both server resources after
            // every foreground connection so a change made while backgrounded
            // is observed without waiting for another event.
            mutableEvents.tryEmit(PatientRealtimeEvent(PatientRealtimeEventType.ROUTINE_UPDATED))
            mutableEvents.tryEmit(PatientRealtimeEvent(PatientRealtimeEventType.SCHEDULE_UPDATED))
        }

        override fun onMessage(webSocket: WebSocket, text: String) {
            val json = runCatching { JSONObject(text) }.getOrNull() ?: return
            val patientId = json.optJSONObject("data")?.optString("patient_id") ?: return
            if (patientId != session.patientId) return
            when (json.optString("event_type")) {
                "routine.updated" -> mutableEvents.tryEmit(PatientRealtimeEvent(PatientRealtimeEventType.ROUTINE_UPDATED))
                "schedule.updated" -> mutableEvents.tryEmit(PatientRealtimeEvent(PatientRealtimeEventType.SCHEDULE_UPDATED))
            }
        }

        override fun onClosing(webSocket: WebSocket, code: Int, reason: String) {
            // OkHttp only finalizes the close handshake (and later calls onClosed) once the
            // client reciprocates; without this, a server-initiated close never completes and
            // scheduleReconnect() would only run after a much later read-timeout failure, if ever.
            webSocket.close(code, reason)
        }

        override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
            scheduleReconnect(session)
        }

        override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {
            scheduleReconnect(session)
        }
    }

    private companion object {
        const val NORMAL_CLOSURE = 1000
        const val RECONNECT_DELAY_MS = 2_000L
    }
}
