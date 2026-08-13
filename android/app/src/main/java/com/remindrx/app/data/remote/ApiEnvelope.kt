package com.remindrx.app.data.remote

/** Khớp src/core/response.py:APIResponse — envelope chung cho mọi endpoint FastAPI, trừ /chat và /chat/voice. */
data class ApiEnvelope<T>(
    val success: Boolean,
    val code: Int,
    val message: String,
    val data: T?,
    val errors: Any?,
)
