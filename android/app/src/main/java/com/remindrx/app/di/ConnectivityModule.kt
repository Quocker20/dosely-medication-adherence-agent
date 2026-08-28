package com.remindrx.app.di

import com.remindrx.app.core.connectivity.AndroidConnectivityObserver
import com.remindrx.app.core.connectivity.ConnectivityObserver
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
