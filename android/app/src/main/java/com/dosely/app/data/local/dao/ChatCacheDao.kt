package com.dosely.app.data.local.dao

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import com.dosely.app.data.local.entity.ChatConversationEntity
import com.dosely.app.data.local.entity.ChatMessageEntity
import kotlinx.coroutines.flow.Flow

@Dao
interface ChatCacheDao {

    @Query("SELECT * FROM chat_conversations WHERE patientId = :patientId ORDER BY updatedAt DESC")
    fun observeConversations(patientId: String): Flow<List<ChatConversationEntity>>

    @Query("SELECT * FROM chat_messages WHERE conversationId = :conversationId ORDER BY createdAt ASC")
    fun observeMessages(conversationId: String): Flow<List<ChatMessageEntity>>

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsertConversations(conversations: List<ChatConversationEntity>)

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsertConversation(conversation: ChatConversationEntity)

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsertMessages(messages: List<ChatMessageEntity>)

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsertMessage(message: ChatMessageEntity)

    @Query("DELETE FROM chat_conversations WHERE patientId = :patientId")
    suspend fun clearConversations(patientId: String)

    @Query("DELETE FROM chat_messages WHERE conversationId = :conversationId")
    suspend fun clearMessages(conversationId: String)
}
