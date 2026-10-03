package com.dosely.app.di

import com.dosely.app.core.PatientRealtimeBaseUrl
import com.dosely.app.core.PatientRealtimeEvents
import com.dosely.app.core.PatientRealtimeSync
import com.dosely.app.data.remote.ApiConfig
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
