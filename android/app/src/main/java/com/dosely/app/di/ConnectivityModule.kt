package com.dosely.app.di

import com.dosely.app.core.connectivity.AndroidConnectivityObserver
import com.dosely.app.core.connectivity.ConnectivityObserver
import dagger.Binds
import dagger.Module
import dagger.hilt.InstallIn
import dagger.hilt.components.SingletonComponent

@Module
@InstallIn(SingletonComponent::class)
abstract class ConnectivityModule {
    @Binds
    abstract fun bindConnectivityObserver(impl: AndroidConnectivityObserver): ConnectivityObserver
}
