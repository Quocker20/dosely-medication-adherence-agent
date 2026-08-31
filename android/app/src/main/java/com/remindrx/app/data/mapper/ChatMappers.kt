package com.remindrx.app.data.mapper

import com.remindrx.app.data.ChatConversation
import com.remindrx.app.data.ChatMessage
import com.remindrx.app.data.ChatRole
import com.remindrx.app.data.local.entity.ChatConversationEntity
import com.remindrx.app.data.local.entity.ChatMessageEntity
import com.remindrx.app.data.remote.ChatConversationListItemDto
import com.remindrx.app.data.remote.ChatMessageItemDto

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
