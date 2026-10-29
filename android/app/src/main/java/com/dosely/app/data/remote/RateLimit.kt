package com.dosely.app.data.remote

import com.google.gson.JsonParser
import retrofit2.HttpException

/**
 * Helpers for HTTP 429 responses (Area 4a): login lockout per phone, the per-IP
 * login limiter, and the chat per-minute / per-day limits.
 *
 * The backend answers with the usual envelope:
 * `{"success":false,"code":429,"message":"...","errors":{"retry_after_seconds":N}}`.
 * Deliberate messages (lockout, daily chat limit) are shown as is; the generic
 * window-limiter text ("Quá N yêu cầu / Ws cho <scope>.") is replaced by our own.
 */
private const val HTTP_TOO_MANY_REQUESTS = 429
private val GENERIC_LIMIT_MESSAGE = Regex("""^Quá \d+ yêu cầu""")

const val CHAT_TOO_FAST_MESSAGE = "Bạn gửi quá nhanh, vui lòng thử lại sau ít giây."
private const val DEFAULT_LOGIN_WAIT_SECONDS = 60

data class RateLimitInfo(
    val message: String?,
    val retryAfterSeconds: Int?,
) {
    /** True for the framework's default text, which must not be shown to patients. */
    val isGenericMessage: Boolean
        get() = message == null || GENERIC_LIMIT_MESSAGE.containsMatchIn(message)
}

data class LoginRateLimit(
    val message: String,
    /** Seconds the login form stays locked (0 when the server did not say). */
    val seconds: Int,
)

/** Parses a 429 [HttpException]; null for any other throwable. */
fun Throwable.rateLimitInfo(): RateLimitInfo? {
    if (this !is HttpException || code() != HTTP_TOO_MANY_REQUESTS) return null
    val raw = runCatching { response()?.errorBody()?.string() }.getOrNull()
    val root = raw?.let { runCatching { JsonParser.parseString(it).asJsonObject }.getOrNull() }
    val message = root?.get("message")?.takeIf { it.isJsonPrimitive }?.asString
    val retryAfter = root?.get("errors")
        ?.takeIf { it.isJsonObject }
        ?.asJsonObject
        ?.get("retry_after_seconds")
        ?.takeIf { it.isJsonPrimitive && it.asJsonPrimitive.isNumber }
        ?.asDouble
        ?.let { kotlin.math.ceil(it).toInt() }
        ?.takeIf { it > 0 }
    return RateLimitInfo(message, retryAfter)
}

/** 429 from POST /auth/login -> message to show and how long to lock the form. */
fun Throwable.loginRateLimit(): LoginRateLimit? {
    val info = rateLimitInfo() ?: return null
    val seconds = info.retryAfterSeconds ?: 0
    if (info.isGenericMessage) {
        val wait = if (seconds > 0) seconds else DEFAULT_LOGIN_WAIT_SECONDS
        return LoginRateLimit("Bạn thao tác quá nhanh, vui lòng thử lại sau $wait giây.", seconds)
    }
    return LoginRateLimit(requireNotNull(info.message), seconds)
}

/** 429 from /chat or /chat/voice -> message for the chat error area; null if not a 429. */
fun Throwable.chatRateLimitMessage(): String? {
    val info = rateLimitInfo() ?: return null
    return if (info.isGenericMessage) CHAT_TOO_FAST_MESSAGE else info.message
}
