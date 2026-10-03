package com.dosely.app.data.mapper

import com.google.gson.FieldNamingPolicy
import com.google.gson.GsonBuilder
import com.dosely.app.data.DoseAction
import com.dosely.app.data.DosePeriod
import com.dosely.app.data.DoseStatus
import com.dosely.app.data.MealRelation
import com.dosely.app.data.SurveySeverity
import com.dosely.app.data.SurveySymptom
import com.dosely.app.data.SymptomCode
import com.dosely.app.data.remote.AdherenceSummaryDto
import com.dosely.app.data.remote.DoseDto
import com.dosely.app.data.remote.MedicationDetailResponseDto
import java.time.LocalDate
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class PatientMappersTest {
    private val wireGson = GsonBuilder()
        .setFieldNamingPolicy(FieldNamingPolicy.LOWER_CASE_WITH_UNDERSCORES)
        .create()

    @Test
    fun `late action is sent as taken with source note and late marker in payload`() {
        val request = DoseAction.LATE.toRequestDto(note = "  Uống sau giờ nhắc  ")

        assertEquals("TAKEN", request.action)
        assertEquals("PATIENT_MOBILE_APP", request.actionSource)
        assertEquals("Uống sau giờ nhắc", request.payload["note"])
        assertEquals(true, request.payload["taken_late"])

        val json = wireGson.toJsonTree(request).asJsonObject
        assertEquals("PATIENT_MOBILE_APP", json["action_source"].asString)
        assertTrue(json["payload"].asJsonObject["taken_late"].asBoolean)
        assertFalse(json.has("note"))
    }

    @Test
    fun `survey mapper nests mood and emits stable symptom wire fields`() {
        val date = LocalDate.of(2026, 8, 14)
        val request = listOf(
            SurveySymptom(
                code = SymptomCode.DIZZINESS,
                severity = SurveySeverity.MODERATE,
                description = "Chóng mặt khi đứng dậy",
            ),
        ).toSurveyRequestDto(mood = 3, surveyDate = date)

        assertEquals("2026-08-14", request.surveyDate)
        assertEquals(3, request.answersJson["mood"])
        assertEquals("DIZZINESS", request.symptoms.single().symptomCode)
        assertEquals("MODERATE", request.symptoms.single().severity)

        val json = wireGson.toJsonTree(request).asJsonObject
        assertEquals(3, json["answers_json"].asJsonObject["mood"].asInt)
        assertEquals("DIZZINESS", json["symptoms"].asJsonArray[0].asJsonObject["symptom_code"].asString)
    }

    @Test
    fun `sos mapper uses message and metadata share_location`() {
        val request = toSosRequestDto(message = "  Cần trợ giúp  ", shareLocation = false)

        assertEquals("Cần trợ giúp", request.message)
        assertEquals(false, request.metadata["share_location"])

        val json = wireGson.toJsonTree(request).asJsonObject
        assertEquals("Cần trợ giúp", json["message"].asString)
        assertFalse(json["metadata"].asJsonObject["share_location"].asBoolean)
        assertFalse(json.has("share_location"))
    }

    @Test
    fun `blank sos message becomes null`() {
        val request = toSosRequestDto(message = "   ", shareLocation = true)

        assertNull(request.message)
        assertEquals(true, request.metadata["share_location"])
    }

    @Test
    fun `adherence mapper preserves fractional rate and all counters`() {
        val summary = AdherenceSummaryDto(
            patientId = "patient-id",
            fromDate = "2026-08-10",
            toDate = "2026-08-14",
            adherenceRate = 87.5f,
            totalDoses = 8,
            takenDoses = 7,
            skippedDoses = 1,
            missedDoses = 0,
        ).toDomain()

        assertEquals(87.5f, summary.adherenceRate, 0f)
        assertEquals(LocalDate.of(2026, 8, 10), summary.fromDate)
        assertEquals(LocalDate.of(2026, 8, 14), summary.toDate)
        assertEquals(8, summary.totalDoses)
        assertEquals(7, summary.takenDoses)
        assertEquals(1, summary.skippedDoses)
        assertEquals(0, summary.missedDoses)
    }

    @Test
    fun `medication detail mapper keeps every backend field`() {
        val detail = MedicationDetailResponseDto(
            id = "medication-id",
            name = "Metformin",
            composition = "Metformin hydrochloride 500 mg",
            manufacturer = "Example Pharma",
            uses = "Hỗ trợ kiểm soát đường huyết",
            sideEffects = "Buồn nôn",
            imageUrl = "https://example.test/metformin.png",
            sourceName = "Drug catalog",
            isActive = true,
        ).toDomain()

        assertEquals("medication-id", detail.id)
        assertEquals("Metformin", detail.name)
        assertEquals("Metformin hydrochloride 500 mg", detail.composition)
        assertEquals("Example Pharma", detail.manufacturer)
        assertEquals("Hỗ trợ kiểm soát đường huyết", detail.uses)
        assertEquals("Buồn nôn", detail.sideEffects)
        assertEquals("https://example.test/metformin.png", detail.imageUrl)
        assertEquals("Drug catalog", detail.sourceName)
        assertTrue(detail.isActive)
    }

    @Test
    fun `schedule mapper uses exact snapshot converts to Vietnam time and keeps missed distinct`() {
        val dose = DoseDto(
            scheduledDoseId = "dose-id",
            prescriptionItemId = "item-id",
            medicationId = "medication-id",
            medicationName = "Metformin",
            currentScheduledAt = "2026-08-14T00:30:00Z",
            doseSlot = "MORNING",
            doseValue = 0.5,
            doseUnit = "viên",
            mealRelation = "AFTER_MEAL",
            status = "MISSED",
            snoozeCount = 0,
        ).toDoseToday()

        assertEquals("07:30", dose.time)
        assertEquals("0.5 viên", dose.doseLabel)
        assertEquals(DosePeriod.MORNING, dose.period)
        assertEquals(MealRelation.AFTER_MEAL, dose.mealRelation)
        assertEquals(DoseStatus.MISSED, dose.status)
        assertEquals("item-id", dose.prescriptionItemId)
        assertEquals("medication-id", dose.medicationId)
        assertEquals(0.5, dose.doseValue ?: Double.NaN, 0.0)
    }

    @Test
    fun `legacy schedule row shows unknown dose instead of guessing prescription amount`() {
        val dose = DoseDto(
            scheduledDoseId = "legacy-dose-id",
            prescriptionItemId = "item-id",
            medicationId = null,
            medicationName = "Thuốc cũ",
            currentScheduledAt = "2026-08-14T05:00:00Z",
            doseSlot = null,
            doseValue = null,
            doseUnit = null,
            mealRelation = null,
            status = "PENDING",
            snoozeCount = 0,
        ).toDoseToday()

        assertEquals("12:00", dose.time)
        assertEquals("Chưa có dữ liệu liều", dose.doseLabel)
        assertEquals(MealRelation.NONE, dose.mealRelation)
        assertEquals(DoseStatus.UPCOMING, dose.status)
    }
}
