package com.remindrx.app.di

import android.content.Context
import androidx.room.Room
import com.remindrx.app.data.local.RemindRxDatabase
import com.remindrx.app.data.local.dao.OutboxDao
import com.remindrx.app.data.local.dao.PatientCacheDao
import dagger.Module
import dagger.Provides
import dagger.hilt.InstallIn
import dagger.hilt.android.qualifiers.ApplicationContext
import dagger.hilt.components.SingletonComponent
import javax.inject.Singleton

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
        ).build()

    @Provides
    fun providePatientCacheDao(database: RemindRxDatabase): PatientCacheDao =
        database.patientCacheDao()

    @Provides
    fun provideOutboxDao(database: RemindRxDatabase): OutboxDao =
        database.outboxDao()
}
