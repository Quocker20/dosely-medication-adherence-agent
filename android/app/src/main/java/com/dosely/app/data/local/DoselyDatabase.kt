package com.dosely.app.data.local

import androidx.room.Database
import androidx.room.RoomDatabase
import androidx.room.TypeConverters
import com.dosely.app.data.local.dao.ChatCacheDao
import com.dosely.app.data.local.dao.OutboxDao
import com.dosely.app.data.local.dao.PatientCacheDao
import com.dosely.app.data.local.entity.AdherenceSummaryEntity
import com.dosely.app.data.local.entity.ChatConversationEntity
import com.dosely.app.data.local.entity.ChatMessageEntity
import com.dosely.app.data.local.entity.DoseTodayEntity
import com.dosely.app.data.local.entity.MedicationEntity
import com.dosely.app.data.local.entity.OutboxActionEntity
import com.dosely.app.data.local.entity.RoutineItemEntity

@Database(
    entities = [
        RoutineItemEntity::class,
        DoseTodayEntity::class,
        MedicationEntity::class,
        AdherenceSummaryEntity::class,
        OutboxActionEntity::class,
        ChatConversationEntity::class,
        ChatMessageEntity::class,
    ],
    version = 2,
    exportSchema = true,
)
@TypeConverters(RoomTypeConverters::class)
abstract class DoselyDatabase : RoomDatabase() {
    abstract fun patientCacheDao(): PatientCacheDao
    abstract fun outboxDao(): OutboxDao
    abstract fun chatCacheDao(): ChatCacheDao
}
