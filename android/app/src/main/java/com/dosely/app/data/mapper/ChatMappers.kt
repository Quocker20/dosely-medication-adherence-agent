package com.dosely.app.data.mapper

import com.dosely.app.data.ChatConversation
import com.dosely.app.data.ChatMessage
import com.dosely.app.data.ChatRole
import com.dosely.app.data.local.entity.ChatConversationEntity
import com.dosely.app.data.local.entity.ChatMessageEntity
import com.dosely.app.data.remote.ChatConversationListItemDto
import com.dosely.app.data.remote.ChatMessageItemDto

fun ChatConversationListItemDto.toEntity(patientId: String): ChatConversationEntity =
    ChatConversationEntity(
        patientId = patientId,
        id = id,
        title = title,
        preview = preview,
        messageCount = messageCount,
        createdAt = createdAt,
        updatedAt = updatedAt,
    )

fun ChatMessageItemDto.toEntity(conversationId: String): ChatMessageEntity =
    ChatMessageEntity(
        conversationId = conversationId,
        id = id,
        role = role,
        content = content,
        intent = intent,
        createdAt = createdAt,
    )

fun ChatConversationEntity.toDomain(messages: List<ChatMessage> = emptyList()): ChatConversation =
    ChatConversation(
        id = id,
        title = title,
        updatedAt = updatedAt,
        messages = messages,
    )

fun ChatMessageEntity.toDomain(): ChatMessage =
    ChatMessage(
        id = id,
        role = if (role.equals("user", ignoreCase = true)) ChatRole.USER else ChatRole.ASSISTANT,
        content = content,
        time = createdAt,
    )
