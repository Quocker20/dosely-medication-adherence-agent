package com.remindrx.app.data.remote

import com.google.gson.annotations.SerializedName

// Khớp src/modules/agents/schemas.py. /chat và /chat/voice bọc trong
// ApiEnvelope như mọi endpoint khác — router gọi success_response()
// (src/modules/agents/router.py), đúng như api-contract.md Slice 6 mô tả.

data class ChatRequestDto(
    val message: String,
    @SerializedName("conversationId")
    val conversationId: String? = null,
    @SerializedName("clientDate")
    val clientDate: String = "",
    @SerializedName("clientDateTime")
    val clientDateTime: String = "",
)

data class ChatResponseDto(
    val response: String,
    @SerializedName("conversationId")
    val conversationId: String? = null,
)

data class VoiceChatResponseDto(
    val transcript: String,
    val response: String,
    @SerializedName("conversationId")
    val conversationId: String? = null,
    // null khi TTS lỗi — backend fail-open, vẫn trả 200 kèm phần chữ.
    val audioBase64: String?,
)

data class ChatConversationListItemDto(
    val id: String,
    val title: String,
    val preview: String? = null,
    @SerializedName("messageCount")
    val messageCount: Int = 0,
    @SerializedName("createdAt")
    val createdAt: String,
    @SerializedName("updatedAt")
    val updatedAt: String,
)

data class ChatMessageItemDto(
    val id: String,
    val role: String,
    val content: String,
    val intent: String? = null,
    @SerializedName("createdAt")
    val createdAt: String,
)

data class ChatConversationDetailDto(
    val id: String,
    val title: String,
    @SerializedName("createdAt")
    val createdAt: String,
    @SerializedName("updatedAt")
    val updatedAt: String,
    val messages: List<ChatMessageItemDto> = emptyList(),
    @SerializedName("hasMore")
    val hasMore: Boolean = false,
    @SerializedName("nextCursor")
    val nextCursor: String? = null,
)
