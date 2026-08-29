package com.remindrx.app.ui.feature.assistant

import android.content.Context
import android.media.MediaPlayer
import android.media.MediaRecorder
import android.os.Build
import android.util.Base64
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.remindrx.app.data.ChatConversation
import com.remindrx.app.data.ChatMessage
import com.remindrx.app.data.ChatRole
import com.remindrx.app.data.DoseToday
import com.remindrx.app.data.repository.ChatRepository
import com.remindrx.app.ui.toVietnameseUiMessage
import dagger.hilt.android.lifecycle.HiltViewModel
import dagger.hilt.android.qualifiers.ApplicationContext
import java.io.File
import java.util.UUID
import javax.inject.Inject
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

data class AssistantUiState(
    val messages: List<ChatMessage> = listOf(welcomeMessage()),
    val conversations: List<ChatConversation> = emptyList(),
    val isReplying: Boolean = false,
    val isRecording: Boolean = false,
    val error: String? = null,
)

@HiltViewModel
class AssistantViewModel @Inject constructor(
    private val repository: ChatRepository,
    @ApplicationContext private val appContext: Context,
) : ViewModel() {
    private val _state = MutableStateFlow(AssistantUiState())
    val state: StateFlow<AssistantUiState> = _state.asStateFlow()

    private var schedule: List<DoseToday> = emptyList()
    private var activeConversationId: String? = null
    private var recorder: MediaRecorder? = null
    private var recordingFile: File? = null
    private var player: MediaPlayer? = null
    private var activePatientId: String? = null
    private var sessionRevision: Long = 0
    private var replyJob: Job? = null

    fun startSession(patientId: String) {
        if (activePatientId == patientId) return
        resetSession(patientId)
    }

    fun endSession() {
        resetSession(null)
    }

    private fun resetSession(patientId: String?) {
        sessionRevision += 1
        activePatientId = patientId
        replyJob?.cancel()
        replyJob = null
        stopRecorderQuietly()
        recordingFile?.delete()
        recordingFile = null
        player?.release()
        player = null
        schedule = emptyList()
        activeConversationId = null
        _state.value = AssistantUiState()
    }

    fun updateScheduleContext(doses: List<DoseToday>) {
        if (activePatientId != null) schedule = doses
    }

    fun sendMessage(content: String) {
        val question = content.trim()
        if (activePatientId == null || question.isBlank() || _state.value.isReplying) return
        appendUserMessage(question)
        val revision = sessionRevision

        replyJob = viewModelScope.launch {
            _state.update { it.copy(isReplying = true, error = null) }
            val conversationId = activeConversationId ?: UUID.randomUUID().toString().also { activeConversationId = it }
            val result = runCatching { repository.sendText(question, conversationId) }
            if (!isCurrentSession(revision)) return@launch
            result
                .onSuccess(::appendAssistantMessage)
                .onFailure { error ->
                    _state.update {
                        it.copy(
                            isReplying = false,
                            error = error.toVietnameseUiMessage("Không nhận được phản hồi từ trợ lý AI."),
                        )
                    }
                }
        }
    }

    /** Bắt đầu ghi âm câu hỏi bằng giọng nói — caller phải đã có quyền RECORD_AUDIO. */
    fun startRecording() {
        if (activePatientId == null || _state.value.isRecording || _state.value.isReplying) return
        val file = File(appContext.cacheDir, "voice-${UUID.randomUUID()}.m4a")
        val mediaRecorder = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            MediaRecorder(appContext)
        } else {
            @Suppress("DEPRECATION")
            MediaRecorder()
        }
        runCatching {
            mediaRecorder.apply {
                setAudioSource(MediaRecorder.AudioSource.MIC)
                setOutputFormat(MediaRecorder.OutputFormat.MPEG_4)
                setAudioEncoder(MediaRecorder.AudioEncoder.AAC)
                setOutputFile(file.absolutePath)
                prepare()
                start()
            }
        }.onSuccess {
            recorder = mediaRecorder
            recordingFile = file
            _state.update { it.copy(isRecording = true, error = null) }
        }.onFailure {
            runCatching { mediaRecorder.release() }
            _state.update { it.copy(error = "Không thể bắt đầu ghi âm. Vui lòng kiểm tra quyền micro.") }
        }
    }

    fun cancelRecording() {
        stopRecorderQuietly()
        recordingFile?.delete()
        recordingFile = null
        _state.update { it.copy(isRecording = false) }
    }

    fun stopRecordingAndSend() {
        if (!_state.value.isRecording) return
        val file = recordingFile
        stopRecorderQuietly()
        recordingFile = null
        _state.update { it.copy(isRecording = false) }
        if (file == null || !file.exists()) return
        val revision = sessionRevision

        replyJob = viewModelScope.launch {
            _state.update { it.copy(isReplying = true, error = null) }
            val conversationId = activeConversationId ?: UUID.randomUUID().toString().also { activeConversationId = it }
            val result = runCatching { repository.sendVoice(file, "audio/mp4", conversationId) }
            if (!isCurrentSession(revision)) {
                file.delete()
                return@launch
            }
            result
                .onSuccess { voiceResult ->
                    appendUserMessage(voiceResult.transcript)
                    appendAssistantMessage(voiceResult.responseText)
                    voiceResult.audioBase64?.let(::playReply)
                }
                .onFailure { error ->
                    _state.update {
                        it.copy(
                            isReplying = false,
                            error = error.toVietnameseUiMessage("Không xử lý được giọng nói. Vui lòng thử lại."),
                        )
                    }
                }
            file.delete()
        }
    }

    fun openConversation(conversationId: String) {
        if (activePatientId == null) return
        val conversation = _state.value.conversations.firstOrNull { it.id == conversationId } ?: return
        activeConversationId = conversationId
        _state.update { it.copy(messages = conversation.messages, isReplying = false) }
    }

    fun startNewConversation() {
        if (activePatientId == null) return
        activeConversationId = null
        _state.update { it.copy(messages = listOf(welcomeMessage()), isReplying = false) }
    }

    private fun stopRecorderQuietly() {
        runCatching { recorder?.stop() }
        runCatching { recorder?.release() }
        recorder = null
    }

    private fun playReply(audioBase64: String) {
        runCatching {
            val bytes = Base64.decode(audioBase64, Base64.DEFAULT)
            val file = File(appContext.cacheDir, "reply-${UUID.randomUUID()}.mp3")
            file.writeBytes(bytes)
            player?.release()
            player = MediaPlayer().apply {
                setDataSource(file.absolutePath)
                setOnCompletionListener {
                    it.release()
                    file.delete()
                }
                prepare()
                start()
            }
        }
    }

    private fun appendUserMessage(content: String) {
        val message = ChatMessage(
            id = UUID.randomUUID().toString(),
            role = ChatRole.USER,
            content = content,
            time = "Bây giờ",
        )
        _state.update { it.copy(messages = it.messages + message) }
    }

    private fun appendAssistantMessage(content: String) {
        val message = ChatMessage(
            id = UUID.randomUUID().toString(),
            role = ChatRole.ASSISTANT,
            content = content,
            time = "Bây giờ",
        )
        _state.update { current ->
            val messages = current.messages + message
            current.copy(
                messages = messages,
                conversations = saveConversation(current.conversations, messages),
                isReplying = false,
            )
        }
    }

    private fun saveConversation(
        conversations: List<ChatConversation>,
        messages: List<ChatMessage>,
    ): List<ChatConversation> {
        val id = activeConversationId ?: UUID.randomUUID().toString().also { activeConversationId = it }
        val title = messages.firstOrNull { it.role == ChatRole.USER }?.content?.take(42) ?: "Cuộc trò chuyện mới"
        val conversation = ChatConversation(id = id, title = title, updatedAt = "Vừa xong", messages = messages)
        return listOf(conversation) + conversations.filterNot { it.id == id }
    }

    private fun isCurrentSession(revision: Long): Boolean =
        activePatientId != null && sessionRevision == revision

    override fun onCleared() {
        super.onCleared()
        replyJob?.cancel()
        stopRecorderQuietly()
        player?.release()
    }
}

internal fun welcomeMessage() = ChatMessage(
    id = "welcome",
    role = ChatRole.ASSISTANT,
    // The local welcome is shown before any /chat call, so it must be neutral.
    // Subsequent backend replies can personalize addressing from patient profile.
    content = "Chào bạn! Tôi có thể giúp xem lịch uống thuốc và giải thích thông tin cơ bản về thuốc trong đơn. Bạn muốn hỏi gì?",
    time = "Bây giờ",
)
