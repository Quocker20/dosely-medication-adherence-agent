package com.remindrx.app.data.repository

import java.io.File

data class VoiceChatResult(val transcript: String, val responseText: String, val audioBase64: String?)

interface ChatRepository {
    suspend fun sendText(message: String): String
    suspend fun sendVoice(audioFile: File, mimeType: String): VoiceChatResult
}
