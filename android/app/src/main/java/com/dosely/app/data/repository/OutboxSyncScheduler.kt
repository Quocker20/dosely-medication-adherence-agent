package com.dosely.app.data.repository

import javax.inject.Inject

interface OutboxSyncScheduler {
    fun scheduleSync()
    fun onConnectivityRestored()
}

class NoOpOutboxSyncScheduler @Inject constructor() : OutboxSyncScheduler {
    override fun scheduleSync() = Unit
    override fun onConnectivityRestored() = Unit
}
