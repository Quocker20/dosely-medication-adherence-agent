package com.remindrx.app.di

import android.content.Context
import androidx.room.Room
import androidx.room.migration.Migration
import androidx.sqlite.db.SupportSQLiteDatabase
import com.remindrx.app.data.local.RemindRxDatabase
import com.remindrx.app.data.local.dao.ChatCacheDao
import com.remindrx.app.data.local.dao.OutboxDao
import com.remindrx.app.data.local.dao.PatientCacheDao
import dagger.Module
import dagger.Provides
import dagger.hilt.InstallIn
import dagger.hilt.android.qualifiers.ApplicationContext
import dagger.hilt.components.SingletonComponent
import javax.inject.Singleton

val MIGRATION_1_2 = object : Migration(1, 2) {
    override fun migrate(db: SupportSQLiteDatabase) {
        db.execSQL(
            """
            CREATE TABLE IF NOT EXISTS `chat_conversations` (
                `patientId` TEXT NOT NULL,
                `id` TEXT NOT NULL,
                `title` TEXT NOT NULL,
                `preview` TEXT,
                `messageCount` INTEGER NOT NULL,
                `createdAt` TEXT NOT NULL,
                `updatedAt` TEXT NOT NULL,
                PRIMARY KEY(`patientId`, `id`)
            )
            """.trimIndent(),
        )
        db.execSQL(
            "CREATE INDEX IF NOT EXISTS `index_chat_conversations_patientId_updatedAt` ON `chat_conversations` (`patientId`, `updatedAt`)",
        )
        db.execSQL(
            """
            CREATE TABLE IF NOT EXISTS `chat_messages` (
                `conversationId` TEXT NOT NULL,
                `id` TEXT NOT NULL,
                `role` TEXT NOT NULL,
                `content` TEXT NOT NULL,
                `intent` TEXT,
                `createdAt` TEXT NOT NULL,
                PRIMARY KEY(`conversationId`, `id`)
            )
            """.trimIndent(),
        )
        db.execSQL(
            "CREATE INDEX IF NOT EXISTS `index_chat_messages_conversationId_createdAt` ON `chat_messages` (`conversationId`, `createdAt`)",
        )
    }
}

@Module
@InstallIn(SingletonComponent::class)
object DatabaseModule {
    @Provides
    @Singleton
    fun provideRemindRxDatabase(@ApplicationContext context: Context): RemindRxDatabase =
        Room.databaseBuilder(
            context,
            RemindRxDatabase::class.java,
            "remindrx.db",
        )
            .addMigrations(MIGRATION_1_2)
            .build()

    @Provides
    fun providePatientCacheDao(database: RemindRxDatabase): PatientCacheDao =
        database.patientCacheDao()

    @Provides
    fun provideOutboxDao(database: RemindRxDatabase): OutboxDao =
        database.outboxDao()

    @Provides
    fun provideChatCacheDao(database: RemindRxDatabase): ChatCacheDao =
        database.chatCacheDao()
}
