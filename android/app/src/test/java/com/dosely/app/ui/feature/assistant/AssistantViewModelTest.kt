package com.dosely.app.ui.feature.assistant

import androidx.test.core.app.ApplicationProvider
import com.dosely.app.data.ChatConversation
import com.dosely.app.data.ChatMessage
import com.dosely.app.data.repository.ChatRepository
import com.dosely.app.data.repository.TextChatResult
import com.dosely.app.data.repository.VoiceChatResult
import com.dosely.app.testing.MainDispatcherRule
import java.io.File
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.ResponseBody.Companion.toResponseBody
import org.robolectric.RobolectricTestRunner
import retrofit2.HttpException
import retrofit2.Response

@RunWith(RobolectricTestRunner::class)
@OptIn(ExperimentalCoroutinesApi::class)
class AssistantViewModelTest {
    @get:Rule
    val mainDispatcherRule = MainDispatcherRule()

    @Test
    fun `second text message reuses conversation id returned by first backend reply`() = runTest {
        val repository = FakeChatRepository(
            textResults = ArrayDeque(
                listOf(
                    TextChatResult(responseText = "Trả lời 1", conversationId = "conv-1"),
                    TextChatResult(responseText = "Trả lời 2", conversationId = "conv-1"),
                ),
            ),
        )
        val viewModel = AssistantViewModel(repository, ApplicationProvider.getApplicationContext())

        viewModel.startSession("patient-1")
        advanceUntilIdle()

        viewModel.sendMessage("Câu đầu")
        advanceUntilIdle()

        viewModel.sendMessage("Câu hai")
        advanceUntilIdle()

        assertEquals(listOf(null, "conv-1"), repository.sentTextConversationIds)
        assertEquals(listOf("Câu đầu", "Câu hai"), repository.sentMessages)
        assertEquals("Trả lời 2", viewModel.state.value.messages.last().content)
    }

    @Test
    fun `daily chat limit 429 shows the server message verbatim`() = runTest {
        val daily = "Bạn đã dùng hết lượt hỏi trợ lý hôm nay, vui lòng quay lại vào ngày mai."
        val repository = FakeChatRepository(textFailure = tooManyRequests(daily))
        val viewModel = AssistantViewModel(repository, ApplicationProvider.getApplicationContext())
        viewModel.startSession("patient-1")
        advanceUntilIdle()

        viewModel.sendMessage("Câu hỏi")
        advanceUntilIdle()

        assertEquals(daily, viewModel.state.value.error)
    }

    @Test
    fun `per-minute chat 429 shows the slow-down text`() = runTest {
        val repository = FakeChatRepository(textFailure = tooManyRequests("Quá 20 yêu cầu / 60s cho chat."))
        val viewModel = AssistantViewModel(repository, ApplicationProvider.getApplicationContext())
        viewModel.startSession("patient-1")
        advanceUntilIdle()

        viewModel.sendMessage("Câu hỏi")
        advanceUntilIdle()

        assertEquals("Bạn gửi quá nhanh, vui lòng thử lại sau ít giây.", viewModel.state.value.error)
    }
}

private fun tooManyRequests(message: String): HttpException = HttpException(
    Response.error<Any>(
        429,
        """{"success":false,"code":429,"message":"$message","data":null,"errors":{"retry_after_seconds":30}}"""
            .toResponseBody("application/json".toMediaType()),
    ),
)

private class FakeChatRepository(
    private val textResults: ArrayDeque<TextChatResult> = ArrayDeque(),
    private val textFailure: Throwable? = null,
) : ChatRepository {
    val sentMessages = mutableListOf<String>()
    val sentTextConversationIds = mutableListOf<String?>()
    private val conversations = MutableStateFlow<List<ChatConversation>>(emptyList())
    private val messages = MutableStateFlow<List<ChatMessage>>(emptyList())

    override fun observeConversations(patientId: String): Flow<List<ChatConversation>> = conversations

    override fun observeMessages(conversationId: String): Flow<List<ChatMessage>> = messages

    override suspend fun refreshConversations(patientId: String, page: Int, size: Int) = Unit

    override suspend fun loadConversationDetail(conversationId: String, limit: Int, before: String?) = Unit

    override suspend fun sendText(message: String, conversationId: String?, patientId: String): TextChatResult {
        sentMessages += message
        sentTextConversationIds += conversationId
        textFailure?.let { throw it }
        return textResults.removeFirst()
    }

    override suspend fun sendVoice(
        audioFile: File,
        mimeType: String,
        conversationId: String?,
        patientId: String,
    ): VoiceChatResult = error("Voice is not used in this test")
}
