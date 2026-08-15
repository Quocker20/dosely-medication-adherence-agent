package com.remindrx.app.data.remote

/** Raised when a successful HTTP response violates the shared API envelope contract. */
class ApiEnvelopeException(message: String) : IllegalStateException(message)

/**
 * Enforces both halves of the backend contract: `success` must be true and a
 * data-bearing endpoint must actually contain data.
 */
fun <T> ApiEnvelope<T>.requireData(operation: String): T {
    if (!success) {
        throw ApiEnvelopeException(message.ifBlank { "$operation không thành công (mã $code)." })
    }
    return data ?: throw ApiEnvelopeException("$operation không trả dữ liệu.")
}
