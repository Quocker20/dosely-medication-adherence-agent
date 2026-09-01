package com.remindrx.app.data.local.entity

import androidx.room.Entity
import androidx.room.Index

@Entity(
    tableName = "chat_conversations",
    primaryKeys = ["patientId", "id"],
    indices = [Index(value = ["patientId", "updatedAt"])],
)
data class ChatConversationEntity(
    val patientId: String,
    val id: String,
    val title: String,
    val preview: String?,
    val messageCount: Int,
    val createdAt: String,
    val updatedAt: String,
)

@Entity(
    tableName = "chat_messages",
    primaryKeys = ["conversationId", "id"],
    indices = [Index(value = ["conversationId", "createdAt"])],
)
data class ChatMessageEntity(
    val conversationId: String,
    val id: String,
    val role: String,
    val content: String,
    val intent: String?,
    val createdAt: String,
)
