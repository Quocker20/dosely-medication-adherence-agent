package com.remindrx.app.data.repository

import com.remindrx.app.data.ChatConversation
import com.remindrx.app.data.ChatMessage
import com.remindrx.app.data.local.dao.ChatCacheDao
import com.remindrx.app.data.local.entity.ChatMessageEntity
import com.remindrx.app.data.mapper.toDomain
import com.remindrx.app.data.mapper.toEntity
import com.remindrx.app.data.remote.ChatRequestDto
import com.remindrx.app.data.remote.RemindRxApiService
import com.remindrx.app.data.remote.requireData
import java.io.File
import java.time.LocalDate
import java.time.OffsetDateTime
import java.util.UUID
import javax.inject.Inject
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map
import okhttp3.MediaType.Companion.toMediaTypeOrNull
import okhttp3.MultipartBody
import okhttp3.RequestBody.Companion.asRequestBody
import okhttp3.RequestBody.Companion.toRequestBody

class RemoteChatRepositoryImpl @Inject constructor(
    private val api: RemindRxApiService,
    private val chatCacheDao: ChatCacheDao,
) : ChatRepository {

    override fun observeConversations(patientId: String): Flow<List<ChatConversation>> =
        chatCacheDao.observeConversations(patientId).map { list ->
            list.map { it.toDomain() }
        }

    override fun observeMessages(conversationId: String): Flow<List<ChatMessage>> =
        chatCacheDao.observeMessages(conversationId).map { list ->
            list.map { it.toDomain() }
        }

    override suspend fun refreshConversations(patientId: String, page: Int, size: Int) {
        val envelope = api.getChatConversations(page = page, size = size)
        val pageResponse = envelope.requireData("Lấy danh sách cuộc trò chuyện")
        val entities = pageResponse.content.map { it.toEntity(patientId) }
        chatCacheDao.upsertConversations(entities)
    }

    override suspend fun loadConversationDetail(conversationId: String, limit: Int, before: String?) {
        val envelope = api.getChatConversationDetail(conversationId = conversationId, limit = limit, before = before)
        val detail = envelope.requireData("Lấy chi tiết cuộc trò chuyện")
        val entities = detail.messages.map { it.toEntity(conversationId) }
        chatCacheDao.upsertMessages(entities)
    }

    override suspend fun sendText(message: String, conversationId: String?, patientId: String): TextChatResult {
        val request = ChatRequestDto(
            message = message,
            conversationId = conversationId,
            clientDate = LocalDate.now().toString(),
            clientDateTime = OffsetDateTime.now().toString(),
        )
        val res = api.sendChatMessage(request).requireData("Gửi tin nhắn")
        val finalConvId = res.conversationId ?: conversationId ?: UUID.randomUUID().toString()
        val now = OffsetDateTime.now().toString()
        chatCacheDao.upsertMessages(
            listOf(
                ChatMessageEntity(
                    conversationId = finalConvId,
                    id = UUID.randomUUID().toString(),
                    role = "user",
                    content = message,
                    intent = null,
                    createdAt = now,
                ),
                ChatMessageEntity(
                    conversationId = finalConvId,
                    id = UUID.randomUUID().toString(),
                    role = "assistant",
                    content = res.response,
                    intent = null,
                    createdAt = now,
                ),
            ),
        )
        runCatching { refreshConversations(patientId) }
        return TextChatResult(responseText = res.response, conversationId = finalConvId)
    }

    override suspend fun sendVoice(
        audioFile: File,
        mimeType: String,
        conversationId: String?,
        patientId: String,
    ): VoiceChatResult {
        val audioBody = audioFile.asRequestBody(mimeType.toMediaTypeOrNull())
        val audioPart = MultipartBody.Part.createFormData("audio", audioFile.name, audioBody)
        val textType = "text/plain".toMediaTypeOrNull()
        val result = api.sendVoiceChatMessage(
            audio = audioPart,
            clientDate = LocalDate.now().toString().toRequestBody(textType),
            clientDateTime = OffsetDateTime.now().toString().toRequestBody(textType),
            conversationId = conversationId?.toRequestBody(textType),
        ).requireData("Gửi tin nhắn thoại")

        val finalConvId = result.conversationId ?: conversationId ?: UUID.randomUUID().toString()
        val now = OffsetDateTime.now().toString()
        chatCacheDao.upsertMessages(
            listOf(
                ChatMessageEntity(
                    conversationId = finalConvId,
                    id = UUID.randomUUID().toString(),
                    role = "user",
                    content = result.transcript,
                    intent = null,
                    createdAt = now,
                ),
                ChatMessageEntity(
                    conversationId = finalConvId,
                    id = UUID.randomUUID().toString(),
                    role = "assistant",
                    content = result.response,
                    intent = null,
                    createdAt = now,
                ),
            ),
        )
        runCatching { refreshConversations(patientId) }
        return VoiceChatResult(
            transcript = result.transcript,
            responseText = result.response,
            audioBase64 = result.audioBase64,
            conversationId = result.conversationId,
        )
    }
}
