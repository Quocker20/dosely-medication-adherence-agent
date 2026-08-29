package com.remindrx.app.data.remote

// Khớp src/modules/agents/schemas.py. /chat và /chat/voice bọc trong
// ApiEnvelope như mọi endpoint khác — router gọi success_response()
// (src/modules/agents/router.py), đúng như api-contract.md Slice 6 mô tả.

data class ChatRequestDto(
    val message: String,
    val conversationId: String? = null,
    val clientDate: String = "",
    val clientDateTime: String = "",
)

data class ChatResponseDto(val response: String, val conversationId: String? = null)

data class VoiceChatResponseDto(
    val transcript: String,
    val response: String,
    val conversationId: String? = null,
    // null khi TTS lỗi — backend fail-open, vẫn trả 200 kèm phần chữ.
    val audioBase64: String?,
)
