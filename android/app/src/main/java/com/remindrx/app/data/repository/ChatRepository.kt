package com.remindrx.app.data.repository

import com.remindrx.app.data.ChatConversation
import com.remindrx.app.data.ChatMessage
import java.io.File
import kotlinx.coroutines.flow.Flow

data class VoiceChatResult(
    val transcript: String,
    val responseText: String,
    val audioBase64: String?,
    val conversationId: String? = null,
)

data class TextChatResult(
    val responseText: String,
    val conversationId: String? = null,
)

interface ChatRepository {
    fun observeConversations(patientId: String): Flow<List<ChatConversation>>
    fun observeMessages(conversationId: String): Flow<List<ChatMessage>>
    suspend fun refreshConversations(patientId: String, page: Int = 1, size: Int = 20)
    suspend fun loadConversationDetail(conversationId: String, limit: Int = 50, before: String? = null)
    suspend fun sendText(message: String, conversationId: String?, patientId: String): TextChatResult
    suspend fun sendVoice(audioFile: File, mimeType: String, conversationId: String?, patientId: String): VoiceChatResult
}
