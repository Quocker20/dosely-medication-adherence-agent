package com.remindrx.app.data.mapper

import com.remindrx.app.data.AdherenceLog
import com.remindrx.app.data.AdherenceSummary
import com.remindrx.app.data.AgentRun
import com.remindrx.app.data.AgentRunRequest
import com.remindrx.app.data.Alert
import com.remindrx.app.data.CaregiverLink
import com.remindrx.app.data.DoseAction
import com.remindrx.app.data.DosePeriod
import com.remindrx.app.data.DoseStatus
import com.remindrx.app.data.DoseToday
import com.remindrx.app.data.HealthSurvey
import com.remindrx.app.data.MealRelation
import com.remindrx.app.data.Medication
import com.remindrx.app.data.MedicationDetail
import com.remindrx.app.data.PageResult
import com.remindrx.app.data.SurveySymptom
import com.remindrx.app.data.remote.AdherenceLogDto
import com.remindrx.app.data.remote.AdherenceSummaryDto
import com.remindrx.app.data.remote.AgentRunAsyncResponseDto
import com.remindrx.app.data.remote.AgentRunStatusResponseDto
import com.remindrx.app.data.remote.AlertDto
import com.remindrx.app.data.remote.CaregiverLinkDetailResponseDto
import com.remindrx.app.data.remote.DoseDto
import com.remindrx.app.data.remote.HealthSurveyDto
import com.remindrx.app.data.remote.MedicationDetailResponseDto
import com.remindrx.app.data.remote.PageResponseDto
import com.remindrx.app.data.remote.PrescriptionDto
import com.remindrx.app.data.remote.PrescriptionItemDto
import com.remindrx.app.data.remote.RecordDoseActionRequestDto
import com.remindrx.app.data.remote.SubmitHealthSurveyRequestDto
import com.remindrx.app.data.remote.SymptomEntryDto
import com.remindrx.app.data.remote.TriggerSosRequestDto
import java.time.LocalDate
import java.time.Instant
import java.time.OffsetDateTime
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.time.temporal.ChronoUnit

fun DoseAction.toRequestDto(note: String? = null): RecordDoseActionRequestDto {
    val wireAction = if (this == DoseAction.LATE) DoseAction.TAKEN.name else name
    val payload = buildMap<String, Any?> {
        note?.trim()?.takeIf(String::isNotEmpty)?.let { put("note", it) }
        if (this@toRequestDto == DoseAction.LATE) put("taken_late", true)
    }
    return RecordDoseActionRequestDto(action = wireAction, payload = payload)
}

fun AdherenceLogDto.toDomain(): AdherenceLog = AdherenceLog(
    id = id,
    scheduledDoseId = scheduledDoseId,
    patientId = patientId,
    action = action,
    performedAt = performedAt,
    actionSource = actionSource,
    payload = payload,
    idempotencyKey = idempotencyKey,
)

fun AdherenceSummaryDto.toDomain(): AdherenceSummary = AdherenceSummary(
    patientId = patientId,
    fromDate = LocalDate.parse(fromDate),
    toDate = LocalDate.parse(toDate),
    adherenceRate = adherenceRate,
    totalDoses = totalDoses,
    takenDoses = takenDoses,
    skippedDoses = skippedDoses,
    missedDoses = missedDoses,
)

fun PageResponseDto<AdherenceLogDto>.toAdherencePage(): PageResult<AdherenceLog> = PageResult(
    content = content.map(AdherenceLogDto::toDomain),
    page = pageNo,
    size = pageSize,
    totalElements = totalElements,
    totalPages = totalPages,
    isLast = last,
)

fun List<SurveySymptom>.toSurveyRequestDto(
    mood: Int,
    surveyDate: LocalDate,
): SubmitHealthSurveyRequestDto = SubmitHealthSurveyRequestDto(
    surveyDate = surveyDate.toString(),
    answersJson = mapOf("mood" to mood),
    symptoms = map { symptom ->
        SymptomEntryDto(
            symptomCode = symptom.code.wireValue,
            severity = symptom.severity.name,
            description = symptom.description,
        )
    },
)

fun HealthSurveyDto.toDomain(): HealthSurvey = HealthSurvey(
    id = id,
    patientId = patientId,
    surveyDate = LocalDate.parse(surveyDate),
    status = status,
    submittedAt = submittedAt,
)

fun toSosRequestDto(message: String?, shareLocation: Boolean): TriggerSosRequestDto =
    TriggerSosRequestDto(
        message = message?.trim()?.takeIf(String::isNotEmpty),
        metadata = mapOf("share_location" to shareLocation),
    )

fun AlertDto.toDomain(): Alert = Alert(
    id = id,
    patientId = patientId,
    assignedDoctorId = assignedDoctorId,
    triggeredByType = triggeredByType,
    alertType = alertType,
    severity = severity,
    status = status,
    message = message,
    createdAt = createdAt,
)

fun CaregiverLinkDetailResponseDto.toDomain(): CaregiverLink =
    CaregiverLink(
        id = id,
        patientId = patientId,
        phone = phone,
        relationship = relationship,
        linkCode = linkCode,
        telegramDeepLink = telegramDeepLink,
        status = status,
        telegramBoundAt = telegramBoundAt,
        lastMessageSentAt = lastMessageSentAt,
        createdAt = createdAt,
    )

fun MedicationDetailResponseDto.toDomain(): MedicationDetail = MedicationDetail(
    id = id,
    name = name,
    composition = composition,
    manufacturer = manufacturer,
    uses = uses,
    sideEffects = sideEffects,
    imageUrl = imageUrl,
    sourceName = sourceName,
    isActive = isActive,
)

fun AgentRunAsyncResponseDto.toDomain(): AgentRunRequest = AgentRunRequest(
    agentRunId = agentRunId,
    status = status,
    message = message,
)

fun AgentRunStatusResponseDto.toDomain(): AgentRun = AgentRun(
    id = id,
    agentType = agentType,
    patientId = patientId,
    prescriptionId = prescriptionId,
    triggerType = triggerType,
    graphVersion = graphVersion,
    status = status,
    latencyMs = latencyMs,
    errorCode = errorCode,
    generatedDoseCount = generatedDoseCount,
    createdAt = createdAt,
)

fun List<PrescriptionDto>.toMedications(): List<Medication> = flatMap { prescription ->
    prescription.items.map { item -> item.toMedication(prescription.id) }
}

private val VIETNAM_ZONE: ZoneId = ZoneId.of("Asia/Ho_Chi_Minh")

fun DoseDto.toDoseToday(): DoseToday {
    val vietnamScheduledAt = runCatching {
        OffsetDateTime.parse(currentScheduledAt).atZoneSameInstant(VIETNAM_ZONE)
    }.getOrNull()
    val time = vietnamScheduledAt?.format(DateTimeFormatter.ofPattern("HH:mm")) ?: "--:--"
    val hour = vietnamScheduledAt?.hour ?: 8
    val isPending = status.equals("PENDING", ignoreCase = true)
    val isNotDueYet = vietnamScheduledAt?.toInstant()?.isAfter(Instant.now()) == true
    return DoseToday(
        id = scheduledDoseId,
        time = time,
        medicationName = medicationName,
        doseLabel = doseValue.toExactDoseLabel(doseUnit),
        mealRelation = mealRelation.toMealRelation(),
        status = if (isPending && isNotDueYet) {
            // The patient must not record an adherence action before the
            // scheduled time. The API enforces this too; this state provides
            // a clear, non-interactive affordance in the app.
            DoseStatus.LOCKED
        } else if (isPending && (snoozeCount ?: 0) > 0) {
            DoseStatus.SNOOZED
        } else {
            status.toDoseStatus()
        },
        period = doseSlot.toDosePeriod(hour),
        // The schedule contract exposes snooze_count, not the duration.
        snoozeMinutes = null,
        prescriptionItemId = prescriptionItemId,
        medicationId = medicationId,
        doseSlot = doseSlot,
        doseValue = doseValue,
        doseUnit = doseUnit,
        currentScheduledAt = currentScheduledAt,
        snoozeCount = snoozeCount ?: 0,
    )
}

private fun PrescriptionItemDto.toMedication(parentPrescriptionId: String): Medication = Medication(
    name = displayName,
    doseLabel = doseLabel(),
    // Exact times are attached by prescription_item_id from ActiveScheduleResponse.
    times = emptyList(),
    remainingDaysLabel = remainingDaysLabel(),
    medicationId = medicationId,
    prescriptionId = parentPrescriptionId,
    prescriptionItemId = id,
    doseUnit = doseUnit,
    morningDose = morningDose,
    noonDose = noonDose,
    eveningDose = eveningDose,
    bedtimeDose = bedtimeDose,
    route = route,
    mealRelation = mealRelation.toMealRelation(),
    minimumIntervalMinutes = minimumIntervalMinutes,
    startDate = startDate,
    endDate = endDate,
    instructions = instructions,
    createdAt = createdAt,
)

private fun PrescriptionItemDto.doseLabel(): String {
    val doses = listOfNotNull(morningDose, noonDose, eveningDose, bedtimeDose).distinct()
    return when (doses.size) {
        0 -> doseUnit
        1 -> "${doses.single().stripTrailingZero()} $doseUnit".trim()
        else -> "${doses.joinToString("/") { it.stripTrailingZero() }} $doseUnit theo cữ".trim()
    }
}

private fun Double.stripTrailingZero(): String =
    if (this == toLong().toDouble()) toLong().toString() else toString()

private fun Double?.toExactDoseLabel(unit: String?): String {
    val normalizedUnit = unit?.trim().orEmpty()
    return if (this != null && normalizedUnit.isNotEmpty()) {
        "${stripTrailingZero()} $normalizedUnit"
    } else {
        // Legacy rows have no safe slot-specific dose snapshot. Be explicit
        // instead of guessing one of the parent item's four dose columns.
        "Chưa có dữ liệu liều"
    }
}

private fun PrescriptionItemDto.remainingDaysLabel(): String {
    val lastDate = endDate ?: return "Dùng theo chỉ định"
    val days = runCatching { ChronoUnit.DAYS.between(LocalDate.now(), LocalDate.parse(lastDate)) }
        .getOrNull() ?: return "Dùng theo chỉ định"
    return if (days >= 0) "Còn $days ngày" else "Đã hết hạn dùng"
}

private fun String?.toMealRelation(): MealRelation = when (this?.uppercase()) {
    "BEFORE_MEAL" -> MealRelation.BEFORE_MEAL
    "AFTER_MEAL" -> MealRelation.AFTER_MEAL
    "WITH_MEAL" -> MealRelation.WITH_MEAL
    else -> MealRelation.NONE
}

private fun String.toDoseStatus(): DoseStatus = when (uppercase()) {
    "TAKEN" -> DoseStatus.TAKEN
    "SKIPPED" -> DoseStatus.SKIPPED
    "MISSED" -> DoseStatus.MISSED
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

private fun String?.toDosePeriod(fallbackHour: Int): DosePeriod = when (this?.uppercase()) {
    "MORNING" -> DosePeriod.MORNING
    "NOON" -> DosePeriod.NOON
    "EVENING", "BEDTIME" -> DosePeriod.EVENING
    else -> fallbackHour.toDosePeriod()
}
