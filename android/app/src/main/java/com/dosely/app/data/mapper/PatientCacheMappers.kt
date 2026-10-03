package com.dosely.app.data.mapper

import com.google.gson.Gson
import com.google.gson.reflect.TypeToken
import com.dosely.app.data.AdherenceSummary
import com.dosely.app.data.DoseToday
import com.dosely.app.data.Medication
import com.dosely.app.data.RoutineItem
import com.dosely.app.data.local.entity.AdherenceSummaryEntity
import com.dosely.app.data.local.entity.DoseTodayEntity
import com.dosely.app.data.local.entity.MedicationEntity
import com.dosely.app.data.local.entity.OutboxRoutineItemPayload
import com.dosely.app.data.local.entity.OutboxSymptomPayload
import com.dosely.app.data.local.entity.RoutineItemEntity
import java.time.LocalDate

private val STRING_LIST_TYPE = object : TypeToken<List<String>>() {}.type

fun List<RoutineItem>.toRoutineEntities(patientId: String): List<RoutineItemEntity> =
    map { item ->
        RoutineItemEntity(
            patientId = patientId,
            key = item.key,
            label = item.label,
            time = item.time,
        )
    }

fun List<RoutineItemEntity>.toRoutineItems(): List<RoutineItem> =
    map { entity ->
        RoutineItem(
            key = entity.key,
            label = entity.label,
            time = entity.time,
        )
    }

fun List<DoseToday>.toDoseEntities(patientId: String, scheduleDate: LocalDate): List<DoseTodayEntity> =
    map { dose ->
        DoseTodayEntity(
            patientId = patientId,
            scheduleDate = scheduleDate.toString(),
            id = dose.id,
            time = dose.time,
            medicationName = dose.medicationName,
            doseLabel = dose.doseLabel,
            mealRelation = dose.mealRelation,
            status = dose.status,
            period = dose.period,
            snoozeMinutes = dose.snoozeMinutes,
            prescriptionItemId = dose.prescriptionItemId,
            medicationId = dose.medicationId,
            doseSlot = dose.doseSlot,
            doseValue = dose.doseValue,
            doseUnit = dose.doseUnit,
            currentScheduledAt = dose.currentScheduledAt,
            snoozeCount = dose.snoozeCount,
        )
    }

fun List<DoseTodayEntity>.toDoseTodayItems(): List<DoseToday> =
    map { entity ->
        DoseToday(
            id = entity.id,
            time = entity.time,
            medicationName = entity.medicationName,
            doseLabel = entity.doseLabel,
            mealRelation = entity.mealRelation,
            status = entity.status,
            period = entity.period,
            snoozeMinutes = entity.snoozeMinutes,
            prescriptionItemId = entity.prescriptionItemId,
            medicationId = entity.medicationId,
            doseSlot = entity.doseSlot,
            doseValue = entity.doseValue,
            doseUnit = entity.doseUnit,
            currentScheduledAt = entity.currentScheduledAt,
            snoozeCount = entity.snoozeCount,
        )
    }

fun List<Medication>.toMedicationEntities(patientId: String, gson: Gson): List<MedicationEntity> =
    map { medication ->
        MedicationEntity(
            patientId = patientId,
            localId = medication.prescriptionItemId ?: medication.medicationId ?: medication.name,
            name = medication.name,
            doseLabel = medication.doseLabel,
            timesJson = gson.toJson(medication.times),
            remainingDaysLabel = medication.remainingDaysLabel,
            medicationId = medication.medicationId,
            prescriptionId = medication.prescriptionId,
            prescriptionItemId = medication.prescriptionItemId,
            doseUnit = medication.doseUnit,
            morningDose = medication.morningDose,
            noonDose = medication.noonDose,
            eveningDose = medication.eveningDose,
            bedtimeDose = medication.bedtimeDose,
            route = medication.route,
            mealRelation = medication.mealRelation,
            minimumIntervalMinutes = medication.minimumIntervalMinutes,
            startDate = medication.startDate,
            endDate = medication.endDate,
            instructions = medication.instructions,
            createdAt = medication.createdAt,
        )
    }

fun List<MedicationEntity>.toMedicationItems(gson: Gson): List<Medication> =
    map { entity ->
        Medication(
            name = entity.name,
            doseLabel = entity.doseLabel,
            times = runCatching {
                gson.fromJson<List<String>>(entity.timesJson, STRING_LIST_TYPE)
            }.getOrDefault(emptyList()),
            remainingDaysLabel = entity.remainingDaysLabel,
            medicationId = entity.medicationId,
            prescriptionId = entity.prescriptionId,
            prescriptionItemId = entity.prescriptionItemId,
            doseUnit = entity.doseUnit,
            morningDose = entity.morningDose,
            noonDose = entity.noonDose,
            eveningDose = entity.eveningDose,
            bedtimeDose = entity.bedtimeDose,
            route = entity.route,
            mealRelation = entity.mealRelation,
            minimumIntervalMinutes = entity.minimumIntervalMinutes,
            startDate = entity.startDate,
            endDate = entity.endDate,
            instructions = entity.instructions,
            createdAt = entity.createdAt,
        )
    }

fun AdherenceSummary.toEntity(patientId: String): AdherenceSummaryEntity =
    AdherenceSummaryEntity(
        patientId = patientId,
        fromDate = fromDate.toString(),
        toDate = toDate.toString(),
        adherenceRate = adherenceRate,
        totalDoses = totalDoses,
        takenDoses = takenDoses,
        skippedDoses = skippedDoses,
        missedDoses = missedDoses,
    )

fun AdherenceSummaryEntity.toDomain(): AdherenceSummary =
    AdherenceSummary(
        patientId = patientId,
        fromDate = LocalDate.parse(fromDate),
        toDate = LocalDate.parse(toDate),
        adherenceRate = adherenceRate,
        totalDoses = totalDoses,
        takenDoses = takenDoses,
        skippedDoses = skippedDoses,
        missedDoses = missedDoses,
    )

fun List<RoutineItem>.toOutboxRoutinePayloads(): List<OutboxRoutineItemPayload> =
    map { item -> OutboxRoutineItemPayload(key = item.key, label = item.label, time = item.time) }

fun List<com.dosely.app.data.SurveySymptom>.toOutboxSymptomPayloads(): List<OutboxSymptomPayload> =
    map { symptom ->
        OutboxSymptomPayload(
            code = symptom.code.wireValue,
            severity = symptom.severity.name,
            description = symptom.description,
        )
    }
