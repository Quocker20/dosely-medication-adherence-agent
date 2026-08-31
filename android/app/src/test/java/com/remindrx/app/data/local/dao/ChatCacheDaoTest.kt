package com.remindrx.app.data.local.dao

import androidx.room.Room
import androidx.test.core.app.ApplicationProvider
import com.remindrx.app.data.local.RemindRxDatabase
import com.remindrx.app.data.local.entity.ChatConversationEntity
import com.remindrx.app.data.local.entity.ChatMessageEntity
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.test.runTest
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner

@RunWith(RobolectricTestRunner::class)
class ChatCacheDaoTest {
    private lateinit var database: RemindRxDatabase
    private lateinit var dao: ChatCacheDao

    @Before
    fun setUp() {
        database = Room.inMemoryDatabaseBuilder(
            ApplicationProvider.getApplicationContext(),
            RemindRxDatabase::class.java,
        )
            .allowMainThreadQueries()
            .build()
        dao = database.chatCacheDao()
    }

    @After
    fun tearDown() {
        database.close()
    }

    @Test
    fun `upserts conversations and messages for offline reads`() = runTest {
        dao.upsertConversations(
            listOf(
                ChatConversationEntity(
                    patientId = "patient-1",
                    id = "conv-old",
                    title = "Cũ",
                    preview = null,
                    messageCount = 0,
                    createdAt = "2026-08-29T10:00:00Z",
                    updatedAt = "2026-08-29T10:00:00Z",
                ),
                ChatConversationEntity(
                    patientId = "patient-1",
                    id = "conv-new",
                    title = "Mới",
                    preview = "Tin mới nhất",
                    messageCount = 2,
                    createdAt = "2026-08-30T10:00:00Z",
                    updatedAt = "2026-08-30T10:05:00Z",
                ),
            ),
        )
        dao.upsertMessages(
            listOf(
                ChatMessageEntity(
                    conversationId = "conv-new",
                    id = "msg-1",
                    role = "user",
                    content = "Tôi uống thuốc lúc nào?",
                    intent = null,
                    createdAt = "2026-08-30T10:00:00Z",
                ),
                ChatMessageEntity(
                    conversationId = "conv-new",
                    id = "msg-2",
                    role = "assistant",
                    content = "Sau ăn sáng.",
                    intent = null,
                    createdAt = "2026-08-30T10:01:00Z",
                ),
            ),
        )

        val conversations = dao.observeConversations("patient-1").first()
        val messages = dao.observeMessages("conv-new").first()

        assertEquals(listOf("conv-new", "conv-old"), conversations.map { it.id })
        assertEquals(listOf("msg-1", "msg-2"), messages.map { it.id })
    }
}
