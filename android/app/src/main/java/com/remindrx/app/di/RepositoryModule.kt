package com.remindrx.app.di

import com.remindrx.app.data.repository.AuthRepository
import com.remindrx.app.data.repository.ChatRepository
import com.remindrx.app.data.repository.PatientRepository
import com.remindrx.app.data.repository.RemoteAuthRepositoryImpl
import com.remindrx.app.data.repository.RemoteChatRepositoryImpl
import com.remindrx.app.data.repository.RemotePatientRepositoryImpl
import com.remindrx.app.data.repository.RemoteRoutineRepositoryImpl
import com.remindrx.app.data.repository.RoutineRepository
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
    abstract fun bindAuthRepository(impl: RemoteAuthRepositoryImpl): AuthRepository

    @Binds
    abstract fun bindRoutineRepository(impl: RemoteRoutineRepositoryImpl): RoutineRepository

    @Binds
    abstract fun bindPatientRepository(impl: RemotePatientRepositoryImpl): PatientRepository

    @Binds
    abstract fun bindChatRepository(impl: RemoteChatRepositoryImpl): ChatRepository
}
