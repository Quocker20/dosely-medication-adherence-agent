package com.remindrx.app.data.local

import androidx.room.Database
import androidx.room.RoomDatabase
import androidx.room.TypeConverters
import com.remindrx.app.data.local.dao.OutboxDao
import com.remindrx.app.data.local.dao.PatientCacheDao
import com.remindrx.app.data.local.entity.AdherenceSummaryEntity
import com.remindrx.app.data.local.entity.DoseTodayEntity
import com.remindrx.app.data.local.entity.MedicationEntity
import com.remindrx.app.data.local.entity.OutboxActionEntity
import com.remindrx.app.data.local.entity.RoutineItemEntity

@Database(
    entities = [
        RoutineItemEntity::class,
        DoseTodayEntity::class,
        MedicationEntity::class,
        AdherenceSummaryEntity::class,
        OutboxActionEntity::class,
    ],
    version = 1,
    exportSchema = true,
)
@TypeConverters(RoomTypeConverters::class)
abstract class RemindRxDatabase : RoomDatabase() {
    abstract fun patientCacheDao(): PatientCacheDao
    abstract fun outboxDao(): OutboxDao
}
