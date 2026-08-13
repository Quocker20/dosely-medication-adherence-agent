package com.remindrx.app.data.repository

import com.remindrx.app.data.DosePeriod
import com.remindrx.app.data.DoseStatus
import com.remindrx.app.data.DoseToday
import com.remindrx.app.data.MealRelation
import com.remindrx.app.data.Medication
import com.remindrx.app.data.RoutineItem
import com.remindrx.app.data.remote.DoseDto
import com.remindrx.app.data.remote.PrescriptionDto
import com.remindrx.app.data.remote.RecordDoseActionRequestDto
import com.remindrx.app.data.remote.RemindRxApiService
import com.remindrx.app.data.remote.SubmitHealthSurveyRequestDto
import com.remindrx.app.data.remote.TriggerSosRequestDto
import java.time.OffsetDateTime
import java.time.format.DateTimeFormatter
import java.util.UUID
import javax.inject.Inject

class RemotePatientRepositoryImpl @Inject constructor(
    private val api: RemindRxApiService,
    private val sessionStore: SessionStore,
    private val routineRepository: RoutineRepository,
) : PatientRepository {

    override suspend fun loadHome(): PatientHome {
        val patientId = sessionStore.requirePatientId()
        val routine = routineRepository.getRoutine()
        val prescriptions = api.getPrescriptions(patientId).data?.content.orEmpty()
        val medications = prescriptions.toMedications()
        val doseLabelByMedication = prescriptions.doseLabelByMedicationName()
        val mealRelationByMedication = prescriptions.mealRelationByMedicationName()
        val doses = api.getSchedule(patientId).data?.doses.orEmpty()
            .map { it.toDoseToday(doseLabelByMedication, mealRelationByMedication) }

        // Slice 7 (adherence) chưa có route thật trên backend — 404 thì tự
        // tính tỉ lệ từ danh sách liều hôm nay thay vì làm hỏng cả màn hình.
        val adherenceRate = runCatching { api.getAdherenceSummary(patientId).data?.adherenceRate }
            .getOrNull()
            ?: computeLocalAdherenceRate(doses)

        return PatientHome(routine = routine, doses = doses, medications = medications, adherenceRate = adherenceRate)
    }

    override suspend fun recordDoseAction(doseId: String, action: String, note: String) {
        api.recordDoseAction(
            scheduledDoseId = doseId,
            idempotencyKey = UUID.randomUUID().toString(),
            request = RecordDoseActionRequestDto(action = action, note = note.ifBlank { null }),
        )
    }

    override suspend fun updateRoutine(routine: List<RoutineItem>): List<RoutineItem> =
        routineRepository.updateRoutine(routine)

    override suspend fun submitHealthSurvey(mood: Int, symptoms: List<String>, severity: String) {
        api.submitHealthSurvey(
            patientId = sessionStore.requirePatientId(),
            request = SubmitHealthSurveyRequestDto(mood = mood, symptoms = symptoms, severity = severity),
        )
    }

    override suspend fun createSos(note: String, shareLocation: Boolean) {
        api.triggerSos(
            patientId = sessionStore.requirePatientId(),
            idempotencyKey = UUID.randomUUID().toString(),
            request = TriggerSosRequestDto(note = note, shareLocation = shareLocation),
        )
    }
}

private fun computeLocalAdherenceRate(doses: List<DoseToday>): Int {
    val resolved = doses.count { it.status in setOf(DoseStatus.TAKEN, DoseStatus.LATE, DoseStatus.SKIPPED) }
    if (resolved == 0) return 100
    val taken = doses.count { it.status == DoseStatus.TAKEN || it.status == DoseStatus.LATE }
    return taken * 100 / resolved
}

private fun List<PrescriptionDto>.toMedications(): List<Medication> = flatMap { prescription ->
    prescription.items.map { item ->
        Medication(
            name = item.displayName,
            doseLabel = item.doseLabel(),
            times = item.scheduledTimes(),
            remainingDaysLabel = item.remainingDaysLabel(),
        )
    }
}

private fun List<PrescriptionDto>.doseLabelByMedicationName(): Map<String, String> =
    flatMap { it.items }.associate { it.displayName to it.doseLabel() }

private fun List<PrescriptionDto>.mealRelationByMedicationName(): Map<String, MealRelation> =
    flatMap { it.items }.associate { it.displayName to it.mealRelation.toMealRelation() }

private fun com.remindrx.app.data.remote.PrescriptionItemDto.doseLabel(): String {
    val dose = morningDose ?: noonDose ?: eveningDose ?: bedtimeDose
    return if (dose != null) "${dose.stripTrailingZero()}$doseUnit" else doseUnit
}

private fun Double.stripTrailingZero(): String =
    if (this == this.toLong().toDouble()) this.toLong().toString() else this.toString()

private fun com.remindrx.app.data.remote.PrescriptionItemDto.scheduledTimes(): List<String> =
    listOfNotNull(
        "07:00".takeIf { morningDose != null },
        "11:30".takeIf { noonDose != null },
        "18:00".takeIf { eveningDose != null },
        "22:00".takeIf { bedtimeDose != null },
    )

private fun com.remindrx.app.data.remote.PrescriptionItemDto.remainingDaysLabel(): String {
    val end = endDate ?: return "Dùng theo chỉ định"
    val days = runCatching {
        java.time.temporal.ChronoUnit.DAYS.between(java.time.LocalDate.now(), java.time.LocalDate.parse(end))
    }.getOrNull() ?: return "Dùng theo chỉ định"
    return if (days >= 0) "Còn $days ngày" else "Đã hết hạn dùng"
}

private fun String?.toMealRelation(): MealRelation = when (this) {
    "BEFORE_MEAL" -> MealRelation.BEFORE_MEAL
    "AFTER_MEAL" -> MealRelation.AFTER_MEAL
    "WITH_MEAL" -> MealRelation.WITH_MEAL
    else -> MealRelation.NONE
}

private fun DoseDto.toDoseToday(
    doseLabelByMedication: Map<String, String>,
    mealRelationByMedication: Map<String, MealRelation>,
): DoseToday {
    val scheduledAt = runCatching { OffsetDateTime.parse(currentScheduledAt) }.getOrNull()
    val time = scheduledAt?.format(DateTimeFormatter.ofPattern("HH:mm")) ?: currentScheduledAt.take(5)
    val hour = scheduledAt?.hour ?: 8
    return DoseToday(
        id = scheduledDoseId,
        time = time,
        medicationName = medicationName,
        doseLabel = doseLabelByMedication[medicationName].orEmpty(),
        mealRelation = mealRelationByMedication[medicationName] ?: MealRelation.NONE,
        status = status.toDoseStatus(),
        period = hour.toDosePeriod(),
        snoozeMinutes = null,
    )
}

// Backend (schedule_tools.py / ScheduledDose.status) dùng PENDING/TAKEN/SKIPPED/MISSED/SNOOZE —
// không có LATE/LOCKED/UPCOMING. Map gần đúng nhất sang model UI hiện có.
private fun String.toDoseStatus(): DoseStatus = when (this) {
    "TAKEN" -> DoseStatus.TAKEN
    "SKIPPED" -> DoseStatus.SKIPPED
    "MISSED" -> DoseStatus.LATE
    "SNOOZE", "SNOOZED" -> DoseStatus.SNOOZED
    "PENDING" -> DoseStatus.UPCOMING
    else -> DoseStatus.LOCKED
}

private fun Int.toDosePeriod(): DosePeriod = when {
    this < 11 -> DosePeriod.MORNING
    this < 14 -> DosePeriod.NOON
    this < 18 -> DosePeriod.AFTERNOON
    else -> DosePeriod.EVENING
}
