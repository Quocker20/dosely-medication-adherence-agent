package com.remindrx.app.data.repository

import com.remindrx.app.data.remote.ChatRequestDto
import com.remindrx.app.data.remote.RemindRxApiService
import java.io.File
import javax.inject.Inject
import okhttp3.MediaType.Companion.toMediaTypeOrNull
import okhttp3.MultipartBody
import okhttp3.RequestBody.Companion.asRequestBody
import okhttp3.RequestBody.Companion.toRequestBody

class RemoteChatRepositoryImpl @Inject constructor(
    private val api: RemindRxApiService,
    private val sessionStore: SessionStore,
) : ChatRepository {

    override suspend fun sendText(message: String): String {
        val request = ChatRequestDto(message = message, patientId = sessionStore.requirePatientId())
        return api.sendChatMessage(request).response
    }

    override suspend fun sendVoice(audioFile: File, mimeType: String): VoiceChatResult {
        val patientIdBody = sessionStore.requirePatientId().toRequestBody("text/plain".toMediaTypeOrNull())
        val audioBody = audioFile.asRequestBody(mimeType.toMediaTypeOrNull())
        val audioPart = MultipartBody.Part.createFormData("audio", audioFile.name, audioBody)
        val result = api.sendVoiceChatMessage(patientIdBody, audioPart)
        return VoiceChatResult(
            transcript = result.transcript,
            responseText = result.response,
            audioBase64 = result.audioBase64,
        )
    }
}
