package com.dosely.app.data.local.dao

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import androidx.room.Transaction
import com.dosely.app.data.local.entity.OutboxActionEntity
import com.dosely.app.data.local.entity.OutboxActionType
import com.dosely.app.data.local.entity.OutboxStatus
import kotlinx.coroutines.flow.Flow

@Dao
abstract class OutboxDao {
    @Insert(onConflict = OnConflictStrategy.REPLACE)
    abstract suspend fun insert(action: OutboxActionEntity)

    @Query(
        """
        DELETE FROM outbox_actions
        WHERE patientId = :patientId
          AND actionType = :actionType
          AND status = :status
        """,
    )
    abstract suspend fun deletePendingByType(
        patientId: String,
        actionType: OutboxActionType,
        status: OutboxStatus = OutboxStatus.PENDING,
    )

    @Query(
        """
        SELECT * FROM outbox_actions
        WHERE patientId = :patientId AND status = :status
        ORDER BY createdAt ASC
        """,
    )
    abstract fun observePending(
        patientId: String,
        status: OutboxStatus = OutboxStatus.PENDING,
    ): Flow<List<OutboxActionEntity>>

    @Query(
        """
        SELECT COUNT(*) FROM outbox_actions
        WHERE patientId = :patientId AND status = :status
        """,
    )
    abstract fun observePendingCount(
        patientId: String,
        status: OutboxStatus = OutboxStatus.PENDING,
    ): Flow<Int>

    /** One-shot read for [com.dosely.app.sync.OutboxSyncWorker] — a worker run drains
     * whatever is pending at the moment it executes, it does not stay subscribed. */
    @Query(
        """
        SELECT * FROM outbox_actions
        WHERE patientId = :patientId AND status = :status
        ORDER BY createdAt ASC
        """,
    )
    abstract suspend fun getPendingOnce(
        patientId: String,
        status: OutboxStatus = OutboxStatus.PENDING,
    ): List<OutboxActionEntity>

    @Query("DELETE FROM outbox_actions WHERE id = :id")
    abstract suspend fun delete(id: String)

    @Query(
        """
        UPDATE outbox_actions
        SET attemptCount = :attemptCount, lastAttemptAt = :attemptedAt, lastError = :lastError
        WHERE id = :id
        """,
    )
    abstract suspend fun recordAttemptFailure(
        id: String,
        attemptCount: Int,
        attemptedAt: Long,
        lastError: String?,
    )

    /** Terminal, non-retryable rejection (e.g. a genuine validation conflict, not a
     * connectivity error) — kept for diagnostics rather than deleted, but excluded
     * from [observePendingCount]/[getPendingOnce] since both default to PENDING. */
    @Query(
        """
        UPDATE outbox_actions
        SET status = 'FAILED', lastAttemptAt = :attemptedAt, lastError = :lastError
        WHERE id = :id
        """,
    )
    abstract suspend fun markFailedTerminal(id: String, attemptedAt: Long, lastError: String?)

    @Transaction
    open suspend fun enqueue(action: OutboxActionEntity) {
        if (action.actionType == OutboxActionType.UPDATE_ROUTINE) {
            deletePendingByType(action.patientId, OutboxActionType.UPDATE_ROUTINE)
        }
        insert(action)
    }
}
