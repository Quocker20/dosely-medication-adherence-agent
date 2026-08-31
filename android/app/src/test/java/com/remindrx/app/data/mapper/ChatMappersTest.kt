package com.remindrx.app.data.mapper

import com.remindrx.app.data.ChatRole
import com.remindrx.app.data.local.entity.ChatConversationEntity
import com.remindrx.app.data.local.entity.ChatMessageEntity
import com.remindrx.app.data.remote.ChatConversationListItemDto
import com.remindrx.app.data.remote.ChatMessageItemDto
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class ChatMappersTest {

    @Test
    fun `ChatConversationListItemDto toEntity maps correctly`() {
        val dto = ChatConversationListItemDto(
            id = "conv-1",
            title = "Hỏi về lịch uống thuốc",
            preview = "Thuốc uống sau ăn nhé",
            messageCount = 2,
            createdAt = "2026-08-30T10:00:00Z",
            updatedAt = "2026-08-30T10:05:00Z",
        )

        val entity = dto.toEntity("patient-1")

        assertEquals("patient-1", entity.patientId)
        assertEquals("conv-1", entity.id)
        assertEquals("Hỏi về lịch uống thuốc", entity.title)
        assertEquals("Thuốc uống sau ăn nhé", entity.preview)
        assertEquals(2, entity.messageCount)
        assertEquals("2026-08-30T10:00:00Z", entity.createdAt)
        assertEquals("2026-08-30T10:05:00Z", entity.updatedAt)
    }

    @Test
    fun `ChatMessageItemDto toEntity maps correctly`() {
        val dto = ChatMessageItemDto(
            id = "msg-1",
            role = "user",
            content = "Tôi nên uống thuốc khi nào?",
            intent = "MEDICATION_QUERY",
            createdAt = "2026-08-30T10:00:00Z",
        )

        val entity = dto.toEntity("conv-1")

        assertEquals("conv-1", entity.conversationId)
        assertEquals("msg-1", entity.id)
        assertEquals("user", entity.role)
        assertEquals("Tôi nên uống thuốc khi nào?", entity.content)
        assertEquals("MEDICATION_QUERY", entity.intent)
        assertEquals("2026-08-30T10:00:00Z", entity.createdAt)
    }

    @Test
    fun `ChatMessageEntity toDomain maps role and time correctly`() {
        val userEntity = ChatMessageEntity(
            conversationId = "conv-1",
            id = "msg-1",
            role = "user",
            content = "Tin nhắn user",
            intent = null,
            createdAt = "2026-08-30T10:00:00Z",
        )
        val assistantEntity = ChatMessageEntity(
            conversationId = "conv-1",
            id = "msg-2",
            role = "assistant",
            content = "Tin nhắn bot",
            intent = null,
            createdAt = "2026-08-30T10:01:00Z",
        )

        val userDomain = userEntity.toDomain()
        val assistantDomain = assistantEntity.toDomain()

        assertEquals(ChatRole.USER, userDomain.role)
        assertEquals("Tin nhắn user", userDomain.content)
        assertEquals("2026-08-30T10:00:00Z", userDomain.time)

        assertEquals(ChatRole.ASSISTANT, assistantDomain.role)
        assertEquals("Tin nhắn bot", assistantDomain.content)
        assertEquals("2026-08-30T10:01:00Z", assistantDomain.time)
    }

    @Test
    fun `ChatConversationEntity toDomain maps properties correctly`() {
        val entity = ChatConversationEntity(
            patientId = "patient-1",
            id = "conv-1",
            title = "Tiêu đề",
            preview = "Xem trước",
            messageCount = 3,
            createdAt = "2026-08-30T10:00:00Z",
            updatedAt = "2026-08-30T10:05:00Z",
        )

        val domain = entity.toDomain()

        assertEquals("conv-1", domain.id)
        assertEquals("Tiêu đề", domain.title)
        assertEquals("2026-08-30T10:05:00Z", domain.updatedAt)
        assertEquals(0, domain.messages.size)
    }
}
