package com.dosely.app.data.repository

import com.google.firebase.messaging.FirebaseMessaging
import javax.inject.Inject
import javax.inject.Singleton
import kotlin.coroutines.resume
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.withTimeoutOrNull

/** This device's current FCM registration token, or null when Firebase cannot supply one. */
fun interface FcmTokenProvider {
    suspend fun currentToken(): String?
}

object NoFcmTokenProvider : FcmTokenProvider {
    override suspend fun currentToken(): String? = null
}

/** Reads the token from FirebaseMessaging; any failure (no Play services, offline) yields null. */
@Singleton
class FirebaseFcmTokenProvider @Inject constructor() : FcmTokenProvider {
    override suspend fun currentToken(): String? = withTimeoutOrNull(TOKEN_TIMEOUT_MS) {
        runCatching {
            suspendCancellableCoroutine<String?> { continuation ->
                FirebaseMessaging.getInstance().token.addOnCompleteListener { task ->
                    if (continuation.isActive) {
                        continuation.resume(if (task.isSuccessful) task.result else null)
                    }
                }
            }
        }.getOrNull()
    }

    private companion object {
        const val TOKEN_TIMEOUT_MS = 3_000L
    }
}
