package com.remindrx.app.data.repository

import com.remindrx.app.data.remote.ChatRequestDto
import com.remindrx.app.data.remote.RemindRxApiService
import com.remindrx.app.data.remote.requireData
import java.io.File
import java.time.LocalDate
import java.time.OffsetDateTime
import javax.inject.Inject
import okhttp3.MediaType.Companion.toMediaTypeOrNull
import okhttp3.MultipartBody
import okhttp3.RequestBody.Companion.asRequestBody
import okhttp3.RequestBody.Companion.toRequestBody

class RemoteChatRepositoryImpl @Inject constructor(
    private val api: RemindRxApiService,
) : ChatRepository {

    override suspend fun sendText(message: String, conversationId: String): String {
        val request = ChatRequestDto(
            message = message,
            conversationId = conversationId,
            clientDate = LocalDate.now().toString(),
            clientDateTime = OffsetDateTime.now().toString(),
        )
        return api.sendChatMessage(request).requireData("Gửi tin nhắn").response
    }

    override suspend fun sendVoice(audioFile: File, mimeType: String, conversationId: String): VoiceChatResult {
        val audioBody = audioFile.asRequestBody(mimeType.toMediaTypeOrNull())
        val audioPart = MultipartBody.Part.createFormData("audio", audioFile.name, audioBody)
        val textType = "text/plain".toMediaTypeOrNull()
        val result = api.sendVoiceChatMessage(
            audioPart,
            LocalDate.now().toString().toRequestBody(textType),
            OffsetDateTime.now().toString().toRequestBody(textType),
            conversationId.toRequestBody(textType),
        ).requireData("Gửi tin nhắn thoại")
        return VoiceChatResult(
            transcript = result.transcript,
            responseText = result.response,
            audioBase64 = result.audioBase64,
        )
    }
}
