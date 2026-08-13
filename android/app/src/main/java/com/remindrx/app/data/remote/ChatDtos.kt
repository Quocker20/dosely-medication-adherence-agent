package com.remindrx.app.data.remote

// Khớp src/models/schemas.py — /chat và /chat/voice trả thẳng model này,
// KHÔNG bọc trong ApiEnvelope (khác mọi endpoint khác của backend).

data class ChatRequestDto(val message: String, val patientId: String)

data class ChatResponseDto(val response: String)

data class VoiceChatResponseDto(
    val transcript: String,
    val response: String,
    val audioBase64: String?,
)
