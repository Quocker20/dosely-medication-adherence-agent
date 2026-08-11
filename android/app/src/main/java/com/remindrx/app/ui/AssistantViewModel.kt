package com.remindrx.app.ui

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.remindrx.app.data.ChatConversation
import com.remindrx.app.data.ChatMessage
import com.remindrx.app.data.ChatRole
import com.remindrx.app.data.DoseStatus
import com.remindrx.app.data.DoseToday
import dagger.hilt.android.lifecycle.HiltViewModel
import java.util.UUID
import javax.inject.Inject
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

data class AssistantUiState(
    val messages: List<ChatMessage> = listOf(welcomeMessage()),
    val conversations: List<ChatConversation> = mockConversations(),
    val isReplying: Boolean = false,
)

@HiltViewModel
class AssistantViewModel @Inject constructor() : ViewModel() {
    private val _state = MutableStateFlow(AssistantUiState())
    val state: StateFlow<AssistantUiState> = _state.asStateFlow()

    private var schedule: List<DoseToday> = emptyList()
    private var activeConversationId: String? = null

    fun updateScheduleContext(doses: List<DoseToday>) {
        schedule = doses
    }

    fun sendMessage(content: String) {
        val question = content.trim()
        if (question.isBlank() || _state.value.isReplying) return

        val userMessage = ChatMessage(
            id = UUID.randomUUID().toString(),
            role = ChatRole.USER,
            content = question,
            time = "Bây giờ",
        )
        _state.update { it.copy(messages = it.messages + userMessage, isReplying = true) }

        viewModelScope.launch {
            delay(550)
            val answer = ChatMessage(
                id = UUID.randomUUID().toString(),
                role = ChatRole.ASSISTANT,
                content = answerFor(question),
                time = "Bây giờ",
            )
            _state.update { current ->
                val messages = current.messages + answer
                current.copy(
                    messages = messages,
                    conversations = saveConversation(current.conversations, messages),
                    isReplying = false,
                )
            }
        }
    }

    fun openConversation(conversationId: String) {
        val conversation = _state.value.conversations.firstOrNull { it.id == conversationId } ?: return
        activeConversationId = conversationId
        _state.update { it.copy(messages = conversation.messages, isReplying = false) }
    }

    fun startNewConversation() {
        activeConversationId = null
        _state.update { it.copy(messages = listOf(welcomeMessage()), isReplying = false) }
    }

    private fun saveConversation(
        conversations: List<ChatConversation>,
        messages: List<ChatMessage>,
    ): List<ChatConversation> {
        val id = activeConversationId ?: UUID.randomUUID().toString().also { activeConversationId = it }
        val title = messages.firstOrNull { it.role == ChatRole.USER }?.content?.take(42) ?: "Cuộc trò chuyện mới"
        val conversation = ChatConversation(id, title, "Vừa xong", messages)
        return listOf(conversation) + conversations.filterNot { it.id == id }
    }

    private fun answerFor(question: String): String {
        val normalized = question.lowercase()
        return when {
            listOf("lịch", "liều tiếp", "hôm nay", "mấy giờ").any(normalized::contains) -> scheduleAnswer()
            "metformin" in normalized -> "Metformin thường được dùng để hỗ trợ kiểm soát đường huyết type 2. Hãy dùng đúng đơn, thường cùng bữa ăn để giảm khó chịu tiêu hoá. Không tự bù gấp đôi nếu quên liều."
            "losartan" in normalized -> "Losartan thường được kê cho tăng huyết áp. Không tự dùng thêm kali hoặc muối thay thế chứa kali khi chưa hỏi bác sĩ."
            "atorvastatin" in normalized -> "Atorvastatin giúp giảm cholesterol và nguy cơ tim mạch ở người phù hợp. Nếu đau hoặc yếu cơ bất thường, hãy báo bác sĩ."
            listOf("quên", "bỏ lỡ", "uống trễ", "uống muộn").any(normalized::contains) -> "Không tự uống gấp đôi để bù. Hãy kiểm tra hướng dẫn trên đơn hoặc liên hệ bác sĩ/dược sĩ, vì cách xử trí phụ thuộc từng thuốc và thời điểm liều kế tiếp."
            listOf("tác dụng phụ", "chóng mặt", "buồn nôn", "khó chịu").any(normalized::contains) -> "Bạn có thể mở tab Đơn thuốc và chọn đúng loại thuốc để xem tác dụng phụ tham khảo. Nếu triệu chứng nặng, khó thở, ngất hoặc đau ngực, hãy tìm trợ giúp y tế ngay."
            else -> "Mình đang chạy dữ liệu AI mock nên chỉ hỗ trợ câu hỏi cơ bản về thuốc và lịch uống. Bạn có thể hỏi: “Liều tiếp theo lúc mấy giờ?”, “Quên liều thì làm gì?” hoặc tên một thuốc trong đơn."
        }
    }

    private fun scheduleAnswer(): String {
        val next = schedule
            .filter { it.status in setOf(DoseStatus.UPCOMING, DoseStatus.SNOOZED, DoseStatus.LOCKED) }
            .minByOrNull { it.time }
        return if (next == null) {
            if (schedule.isEmpty()) {
                "Hôm nay chưa có lịch thuốc. Lịch sẽ xuất hiện sau khi bác sĩ duyệt đơn."
            } else {
                "Bạn không còn liều thuốc nào đang chờ hôm nay."
            }
        } else {
            "Liều tiếp theo là ${next.medicationName}, ${next.doseLabel}, lúc ${next.time}. Hãy làm theo hướng dẫn bữa ăn trên màn Lịch uống thuốc."
        }
    }
}

private fun welcomeMessage() = ChatMessage(
    id = "welcome",
    role = ChatRole.ASSISTANT,
    content = "Chào bác! Tôi có thể giúp xem lịch uống thuốc và giải thích thông tin cơ bản về thuốc trong đơn. Bác muốn hỏi gì?",
    time = "Bây giờ",
)

private fun mockConversations(): List<ChatConversation> = listOf(
    ChatConversation(
        id = "history-missed-dose",
        title = "Quên liều buổi trưa",
        updatedAt = "Hôm qua · 12:42",
        messages = listOf(
            ChatMessage("h1-u", ChatRole.USER, "Tôi quên liều buổi trưa thì làm sao?", "12:40"),
            ChatMessage("h1-a", ChatRole.ASSISTANT, "Không tự uống gấp đôi. Hãy kiểm tra thời gian đến liều kế tiếp và gọi bác sĩ/dược sĩ nếu chưa rõ cách xử trí cho đúng thuốc.", "12:42"),
        ),
    ),
    ChatConversation(
        id = "history-metformin",
        title = "Cách dùng Metformin",
        updatedAt = "08/08/2026 · 07:10",
        messages = listOf(
            ChatMessage("h2-u", ChatRole.USER, "Metformin nên uống lúc nào?", "07:09"),
            ChatMessage("h2-a", ChatRole.ASSISTANT, "Dùng đúng theo đơn. Metformin thường được dùng cùng bữa ăn để giảm khó chịu tiêu hoá.", "07:10"),
        ),
    ),
)
