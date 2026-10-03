package com.dosely.app.di

import com.dosely.app.data.repository.AuthRepository
import com.dosely.app.data.repository.AppUpdateRepository
import com.dosely.app.data.repository.ChatRepository
import com.dosely.app.data.repository.OutboxSyncScheduler
import com.dosely.app.data.repository.PatientRepository
import com.dosely.app.data.repository.PatientReadableCacheCleaner
import com.dosely.app.data.repository.RemoteAuthRepositoryImpl
import com.dosely.app.data.repository.RemoteAppUpdateRepositoryImpl
import com.dosely.app.data.repository.RemoteChatRepositoryImpl
import com.dosely.app.data.repository.RemotePatientRepositoryImpl
import com.dosely.app.data.repository.RemoteRoutineRepositoryImpl
import com.dosely.app.data.repository.RoomPatientReadableCacheCleaner
import com.dosely.app.data.repository.RoutineRepository
import com.dosely.app.sync.WorkManagerOutboxSyncScheduler
import dagger.Binds
import dagger.Module
import dagger.hilt.InstallIn
import dagger.hilt.components.SingletonComponent

/**
 * App MVP dùng API FastAPI thật. Các repository mock vẫn được giữ cho preview
 * và unit test thuần UI, nhưng runtime không còn đọc dữ liệu giả.
 */
@Module
@InstallIn(SingletonComponent::class)
abstract class RepositoryModule {

    @Binds
    abstract fun bindAppUpdateRepository(impl: RemoteAppUpdateRepositoryImpl): AppUpdateRepository

    @Binds
    abstract fun bindAuthRepository(impl: RemoteAuthRepositoryImpl): AuthRepository

    @Binds
    abstract fun bindRoutineRepository(impl: RemoteRoutineRepositoryImpl): RoutineRepository

    @Binds
    abstract fun bindPatientRepository(impl: RemotePatientRepositoryImpl): PatientRepository

    @Binds
    abstract fun bindChatRepository(impl: RemoteChatRepositoryImpl): ChatRepository

    @Binds
    abstract fun bindOutboxSyncScheduler(impl: WorkManagerOutboxSyncScheduler): OutboxSyncScheduler

    @Binds
    abstract fun bindPatientReadableCacheCleaner(
        impl: RoomPatientReadableCacheCleaner,
    ): PatientReadableCacheCleaner
}
