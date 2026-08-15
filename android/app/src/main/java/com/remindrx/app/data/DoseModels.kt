package com.remindrx.app.data

enum class DoseStatus { UPCOMING, LOCKED, SNOOZED, TAKEN, LATE, SKIPPED, MISSED }

enum class MealRelation { NONE, BEFORE_MEAL, AFTER_MEAL, WITH_MEAL }

enum class DosePeriod(val label: String) {
    MORNING("Buổi sáng"),
    NOON("Buổi trưa"),
    AFTERNOON("Buổi chiều"),
    EVENING("Buổi tối"),
}

data class DoseToday(
    val id: String,
    val time: String,
    val medicationName: String,
    val doseLabel: String,
    val mealRelation: MealRelation,
    val status: DoseStatus,
    val period: DosePeriod,
    val snoozeMinutes: Int? = null,
    val prescriptionItemId: String? = null,
    val medicationId: String? = null,
    val doseSlot: String? = null,
    val doseValue: Double? = null,
    val doseUnit: String? = null,
    val currentScheduledAt: String? = null,
    val snoozeCount: Int = 0,
)
