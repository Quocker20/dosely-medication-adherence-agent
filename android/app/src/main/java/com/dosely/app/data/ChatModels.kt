package com.dosely.app.data

enum class ChatRole { USER, ASSISTANT }

data class ChatMessage(
    val id: String,
    val role: ChatRole,
    val content: String,
    val time: String,
)

data class ChatConversation(
    val id: String,
    val title: String,
    val updatedAt: String,
    val messages: List<ChatMessage>,
) {
    val preview: String
        get() = messages.lastOrNull { it.role == ChatRole.ASSISTANT }?.content
            ?: messages.lastOrNull()?.content.orEmpty()
}
