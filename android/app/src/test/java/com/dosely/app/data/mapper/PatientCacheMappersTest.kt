package com.dosely.app.data.mapper

import com.google.gson.Gson
import com.dosely.app.data.AdherenceSummary
import com.dosely.app.data.DosePeriod
import com.dosely.app.data.DoseStatus
import com.dosely.app.data.DoseToday
import com.dosely.app.data.MealRelation
import com.dosely.app.data.Medication
import com.dosely.app.data.RoutineItem
import java.time.LocalDate
import org.junit.Assert.assertEquals
import org.junit.Test

class PatientCacheMappersTest {
    private val gson = Gson()

    @Test
    fun `routine cache mapping preserves keys labels and times`() {
        val routine = listOf(RoutineItem("wake_time", "Thức dậy", "06:30"))

        val roundTrip = routine.toRoutineEntities("patient-1").toRoutineItems()

        assertEquals(routine, roundTrip)
    }

    @Test
    fun `dose cache mapping preserves clinical display fields`() {
        val dose = DoseToday(
            id = "dose-1",
            time = "07:00",
            medicationName = "Aspirin",
            doseLabel = "1 viên",
            mealRelation = MealRelation.AFTER_MEAL,
            status = DoseStatus.UPCOMING,
            period = DosePeriod.MORNING,
            prescriptionItemId = "item-1",
            medicationId = "medication-1",
            doseSlot = "MORNING",
            doseValue = 1.0,
            doseUnit = "viên",
            currentScheduledAt = "2026-08-28T00:00:00Z",
        )

        val roundTrip = listOf(dose)
            .toDoseEntities("patient-1", LocalDate.of(2026, 8, 28))
            .toDoseTodayItems()
            .single()

        assertEquals(dose, roundTrip)
    }

    @Test
    fun `medication cache mapping preserves times json`() {
        val medication = Medication(
            name = "Aspirin",
            doseLabel = "1 viên",
            times = listOf("07:00", "19:00"),
            remainingDaysLabel = "Còn 7 ngày",
            medicationId = "medication-1",
            prescriptionItemId = "item-1",
        )

        val roundTrip = listOf(medication)
            .toMedicationEntities("patient-1", gson)
            .toMedicationItems(gson)
            .single()

        assertEquals(medication, roundTrip)
    }

    @Test
    fun `adherence summary cache mapping preserves date range`() {
        val summary = AdherenceSummary(
            patientId = "patient-1",
            fromDate = LocalDate.of(2026, 8, 24),
            toDate = LocalDate.of(2026, 8, 28),
            adherenceRate = 80f,
            totalDoses = 10,
            takenDoses = 8,
            skippedDoses = 1,
            missedDoses = 1,
        )

        assertEquals(summary, summary.toEntity("patient-1").toDomain())
    }
}
