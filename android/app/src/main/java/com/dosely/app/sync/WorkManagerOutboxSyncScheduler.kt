package com.dosely.app.sync

import android.content.Context
import androidx.work.BackoffPolicy
import androidx.work.Constraints
import androidx.work.ExistingWorkPolicy
import androidx.work.NetworkType
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkRequest
import com.dosely.app.data.repository.OutboxSyncScheduler
import dagger.hilt.android.qualifiers.ApplicationContext
import java.util.concurrent.TimeUnit
import javax.inject.Inject

/**
 * Real Phase 2 scheduler: enqueues a NetworkType.CONNECTED-constrained worker. WorkManager
 * itself holds the request until connectivity is actually available — including across app
 * kill/restart — so [onConnectivityRestored] is a best-effort nudge, not the only trigger:
 * [scheduleSync] alone (called right after every offline enqueue) is already sufficient even
 * if the app is closed before connectivity returns.
 */
class WorkManagerOutboxSyncScheduler @Inject constructor(
    @ApplicationContext private val context: Context,
) : OutboxSyncScheduler {

    override fun scheduleSync() = enqueue()

    override fun onConnectivityRestored() = enqueue()

    private fun enqueue() {
        val request = OneTimeWorkRequestBuilder<OutboxSyncWorker>()
            .setConstraints(
                Constraints.Builder()
                    .setRequiredNetworkType(NetworkType.CONNECTED)
                    .build(),
            )
            .setBackoffCriteria(
                BackoffPolicy.EXPONENTIAL,
                WorkRequest.MIN_BACKOFF_MILLIS,
                TimeUnit.MILLISECONDS,
            )
            .build()
        WorkManager.getInstance(context).enqueueUniqueWork(
            OutboxSyncWorker.UNIQUE_WORK_NAME,
            ExistingWorkPolicy.KEEP,
            request,
        )
    }
}
