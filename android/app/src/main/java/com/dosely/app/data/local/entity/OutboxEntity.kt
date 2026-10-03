package com.dosely.app.data.local.entity

import androidx.room.Entity
import androidx.room.Index
import androidx.room.PrimaryKey

enum class OutboxActionType {
    RECORD_DOSE_ACTION,
    SUBMIT_SURVEY,
    UPDATE_ROUTINE,
    CREATE_SOS,
    CREATE_CAREGIVER,
    DELETE_CAREGIVER,
}

enum class OutboxStatus { PENDING, SYNCED, FAILED }

@Entity(
    tableName = "outbox_actions",
    indices = [
        Index(value = ["patientId", "status"]),
        Index(value = ["patientId", "actionType"]),
    ],
)
data class OutboxActionEntity(
    @PrimaryKey val id: String,
    val patientId: String,
    val actionType: OutboxActionType,
    val payloadJson: String,
    val status: OutboxStatus = OutboxStatus.PENDING,
    val createdAt: Long,
    val attemptCount: Int = 0,
    val lastAttemptAt: Long? = null,
    val lastError: String? = null,
)
