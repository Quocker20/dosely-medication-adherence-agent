package com.remindrx.app.data.local.dao

import androidx.room.Room
import androidx.test.platform.app.InstrumentationRegistry
import com.remindrx.app.data.DosePeriod
import com.remindrx.app.data.DoseStatus
import com.remindrx.app.data.MealRelation
import com.remindrx.app.data.local.RemindRxDatabase
import com.remindrx.app.data.local.entity.AdherenceSummaryEntity
import com.remindrx.app.data.local.entity.DoseTodayEntity
import com.remindrx.app.data.local.entity.MedicationEntity
import com.remindrx.app.data.local.entity.RoutineItemEntity
import kotlinx.coroutines.runBlocking
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Before
import org.junit.Test

class PatientCacheDaoTest {
    private lateinit var database: RemindRxDatabase
    private lateinit var dao: PatientCacheDao

    @Before
    fun setUp() {
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        database = Room.inMemoryDatabaseBuilder(context, RemindRxDatabase::class.java).build()
        dao = database.patientCacheDao()
    }

    @After
    fun tearDown() {
        database.close()
    }

    @Test
    fun replaceHomeCache_replacesPatientScopedHomeRows() = runBlocking {
        dao.replaceHomeCache(
            patientId = "patient-1",
            scheduleDate = "2026-08-28",
            routine = listOf(RoutineItemEntity("patient-1", "wake_time", "Thức dậy", "06:30")),
            doses = listOf(testDose("patient-1", "dose-1", DoseStatus.UPCOMING)),
            medications = listOf(testMedication("patient-1", "med-1")),
            adherenceSummary = AdherenceSummaryEntity(
                patientId = "patient-1",
                fromDate = "2026-08-24",
                toDate = "2026-08-28",
                adherenceRate = 80f,
                totalDoses = 10,
                takenDoses = 8,
                skippedDoses = 1,
                missedDoses = 1,
            ),
        )
        dao.replaceHomeCache(
            patientId = "patient-1",
            scheduleDate = "2026-08-28",
            routine = listOf(RoutineItemEntity("patient-1", "wake_time", "Thức dậy", "07:00")),
            doses = listOf(testDose("patient-1", "dose-2", DoseStatus.TAKEN)),
            medications = listOf(testMedication("patient-1", "med-2")),
            adherenceSummary = AdherenceSummaryEntity(
                patientId = "patient-1",
                fromDate = "2026-08-24",
                toDate = "2026-08-28",
                adherenceRate = 100f,
                totalDoses = 1,
                takenDoses = 1,
                skippedDoses = 0,
                missedDoses = 0,
            ),
        )

        assertEquals("07:00", dao.getRoutine("patient-1").single().time)
        assertEquals("dose-2", dao.getDoses("patient-1", "2026-08-28").single().id)
        assertEquals("med-2", dao.getMedications("patient-1").single().localId)
        assertEquals(
            100f,
            dao.getAdherenceSummary("patient-1", "2026-08-24", "2026-08-28")?.adherenceRate,
        )
    }

    private fun testDose(patientId: String, doseId: String, status: DoseStatus) = DoseTodayEntity(
        patientId = patientId,
        scheduleDate = "2026-08-28",
        id = doseId,
        time = "07:00",
        medicationName = "Aspirin",
        doseLabel = "1 viên",
        mealRelation = MealRelation.AFTER_MEAL,
        status = status,
        period = DosePeriod.MORNING,
        snoozeMinutes = null,
        prescriptionItemId = "item-1",
        medicationId = "medication-1",
        doseSlot = "MORNING",
        doseValue = 1.0,
        doseUnit = "viên",
        currentScheduledAt = "2026-08-28T00:00:00Z",
        snoozeCount = 0,
    )

    private fun testMedication(patientId: String, localId: String) = MedicationEntity(
        patientId = patientId,
        localId = localId,
        name = "Aspirin",
        doseLabel = "1 viên",
        timesJson = """["07:00"]""",
        remainingDaysLabel = "Còn 7 ngày",
        medicationId = "medication-1",
        prescriptionId = "prescription-1",
        prescriptionItemId = localId,
        doseUnit = "viên",
        morningDose = 1.0,
        noonDose = null,
        eveningDose = null,
        bedtimeDose = null,
        route = "ORAL",
        mealRelation = MealRelation.AFTER_MEAL,
        minimumIntervalMinutes = null,
        startDate = "2026-08-28",
        endDate = null,
        instructions = null,
        createdAt = "2026-08-28T00:00:00Z",
    )
}
