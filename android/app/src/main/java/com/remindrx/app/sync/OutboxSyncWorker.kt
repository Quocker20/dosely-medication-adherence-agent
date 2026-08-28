package com.remindrx.app.sync

import android.content.Context
import androidx.hilt.work.HiltWorker
import androidx.work.CoroutineWorker
import androidx.work.WorkerParameters
import com.remindrx.app.data.local.dao.OutboxDao
import com.remindrx.app.data.repository.SessionStore
import dagger.assisted.Assisted
import dagger.assisted.AssistedInject

/**
 * Drains the current patient's outbox once per run — see docs/outbox-replay-contract.md.
 * Deliberately thin: all branching/HTTP logic lives in [OutboxReplayer] so it stays
 * unit-testable without a Context (this class itself has no test of its own, matching the
 * DAO precedent of pushing anything Context-dependent out of the JVM test surface).
 */
@HiltWorker
class OutboxSyncWorker @AssistedInject constructor(
    @Assisted context: Context,
    @Assisted params: WorkerParameters,
    private val outboxDao: OutboxDao,
    private val sessionStore: SessionStore,
    private val replayer: OutboxReplayer,
) : CoroutineWorker(context, params) {

    override suspend fun doWork(): Result {
        val patientId = sessionStore.patientId ?: return Result.success()
        val pending = outboxDao.getPendingOnce(patientId)
        if (pending.isEmpty()) return Result.success()

        var anyRetryable = false
        for (row in pending) {
            when (val outcome = replayer.replay(patientId, row)) {
                ReplayOutcome.Synced -> outboxDao.delete(row.id)
                ReplayOutcome.Retryable -> {
                    anyRetryable = true
                    outboxDao.recordAttemptFailure(
                        id = row.id,
                        attemptCount = row.attemptCount + 1,
                        attemptedAt = System.currentTimeMillis(),
                        lastError = null,
                    )
                }
                is ReplayOutcome.Failed -> outboxDao.markFailedTerminal(
                    id = row.id,
                    attemptedAt = System.currentTimeMillis(),
                    lastError = outcome.reason,
                )
            }
        }
        return if (anyRetryable) Result.retry() else Result.success()
    }

    companion object {
        const val UNIQUE_WORK_NAME = "outbox_sync"
    }
}
