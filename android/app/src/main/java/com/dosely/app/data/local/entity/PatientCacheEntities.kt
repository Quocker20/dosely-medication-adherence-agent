package com.dosely.app.data.local.entity

import androidx.room.Entity
import androidx.room.Index
import com.dosely.app.data.DosePeriod
import com.dosely.app.data.DoseStatus
import com.dosely.app.data.MealRelation

@Entity(
    tableName = "routine_items",
    primaryKeys = ["patientId", "key"],
)
data class RoutineItemEntity(
    val patientId: String,
    val key: String,
    val label: String,
    val time: String,
)

@Entity(
    tableName = "doses_today",
    primaryKeys = ["patientId", "id"],
    indices = [Index(value = ["patientId", "scheduleDate"])],
)
data class DoseTodayEntity(
    val patientId: String,
    val scheduleDate: String,
    val id: String,
    val time: String,
    val medicationName: String,
    val doseLabel: String,
    val mealRelation: MealRelation,
    val status: DoseStatus,
    val period: DosePeriod,
    val snoozeMinutes: Int?,
    val prescriptionItemId: String?,
    val medicationId: String?,
    val doseSlot: String?,
    val doseValue: Double?,
    val doseUnit: String?,
    val currentScheduledAt: String?,
    val snoozeCount: Int,
)

@Entity(
    tableName = "medications",
    primaryKeys = ["patientId", "localId"],
)
data class MedicationEntity(
    val patientId: String,
    val localId: String,
    val name: String,
    val doseLabel: String,
    val timesJson: String,
    val remainingDaysLabel: String,
    val medicationId: String?,
    val prescriptionId: String?,
    val prescriptionItemId: String?,
    val doseUnit: String,
    val morningDose: Double?,
    val noonDose: Double?,
    val eveningDose: Double?,
    val bedtimeDose: Double?,
    val route: String,
    val mealRelation: MealRelation,
    val minimumIntervalMinutes: Int?,
    val startDate: String?,
    val endDate: String?,
    val instructions: String?,
    val createdAt: String?,
)

@Entity(
    tableName = "adherence_summaries",
    primaryKeys = ["patientId", "fromDate", "toDate"],
)
data class AdherenceSummaryEntity(
    val patientId: String,
    val fromDate: String,
    val toDate: String,
    val adherenceRate: Float,
    val totalDoses: Int,
    val takenDoses: Int,
    val skippedDoses: Int,
    val missedDoses: Int,
)
