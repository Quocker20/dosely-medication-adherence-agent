package com.dosely.app.data

/** A prescribed medication row shown in the patient app. */
data class Medication(
    // Keep the original four fields first so existing previews remain source-compatible.
    val name: String,
    val doseLabel: String,
    val times: List<String>,
    val remainingDaysLabel: String,
    val medicationId: String? = null,
    val prescriptionId: String? = null,
    val prescriptionItemId: String? = null,
    val doseUnit: String = "",
    val morningDose: Double? = null,
    val noonDose: Double? = null,
    val eveningDose: Double? = null,
    val bedtimeDose: Double? = null,
    val route: String = "ORAL",
    val mealRelation: MealRelation = MealRelation.NONE,
    val minimumIntervalMinutes: Int? = null,
    val startDate: String? = null,
    val endDate: String? = null,
    val instructions: String? = null,
    val createdAt: String? = null,
)

/** Full catalog data returned by GET /medications/{medication_id}. */
data class MedicationDetail(
    val id: String,
    val name: String,
    val composition: String?,
    val manufacturer: String?,
    val uses: String?,
    val sideEffects: String?,
    val imageUrl: String?,
    val sourceName: String,
    val isActive: Boolean,
)
