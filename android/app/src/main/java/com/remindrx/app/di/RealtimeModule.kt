package com.remindrx.app.di

import com.remindrx.app.core.PatientRealtimeBaseUrl
import com.remindrx.app.core.PatientRealtimeEvents
import com.remindrx.app.core.PatientRealtimeSync
import com.remindrx.app.data.remote.ApiConfig
import dagger.Binds
import dagger.Module
import dagger.Provides
import dagger.hilt.InstallIn
import dagger.hilt.components.SingletonComponent
import javax.inject.Singleton
import okhttp3.HttpUrl
import okhttp3.HttpUrl.Companion.toHttpUrl

@Module
@InstallIn(SingletonComponent::class)
abstract class RealtimeModule {
    @Binds
    @Singleton
    abstract fun bindPatientRealtimeEvents(implementation: PatientRealtimeSync): PatientRealtimeEvents

    companion object {
        @Provides
        @Singleton
        @PatientRealtimeBaseUrl
        fun providePatientRealtimeBaseUrl(): HttpUrl = ApiConfig.BASE_URL.toHttpUrl()
    }
}
