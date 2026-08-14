package com.remindrx.app.data.repository

import com.remindrx.app.data.AdherenceLog
import com.remindrx.app.data.AdherenceSummary
import com.remindrx.app.data.Alert
import com.remindrx.app.data.CaregiverLink
import com.remindrx.app.data.DoseAction
import com.remindrx.app.data.DoseToday
import com.remindrx.app.data.HealthSurvey
import com.remindrx.app.data.Medication
import com.remindrx.app.data.MedicationDetail
import com.remindrx.app.data.OnboardingResult
import com.remindrx.app.data.PageResult
import com.remindrx.app.data.PatientSex
import com.remindrx.app.data.RoutineItem
import com.remindrx.app.data.RoutineUpdateResult
import com.remindrx.app.data.SurveySymptom
import java.time.LocalDate
import kotlin.math.roundToInt

data class PatientHome(
    val routine: List<RoutineItem>,
    val doses: List<DoseToday>,
    val medications: List<Medication>,
    val adherence: AdherenceSummary,
) {
    val adherenceRate: Int
        get() = adherence.adherenceRate.roundToInt().coerceIn(0, 100)
}

interface PatientRepository {
    /** Used to decide routine-only onboarding independently from first-login PIN state. */
    suspend fun getRoutine(): List<RoutineItem>

    /**
     * First-login self-onboarding: writes profile details and the initial routine
     * in one call. The backend takes patient_id from the access token, so this
     * only ever writes the caller's own record.
     */
    suspend fun onboard(
        name: String,
        routine: List<RoutineItem>,
        dob: LocalDate? = null,
        sex: PatientSex? = null,
        emergencyNote: String? = null,
        timezone: String = "Asia/Ho_Chi_Minh",
    ): OnboardingResult

    suspend fun loadHome(): PatientHome

    suspend fun recordDoseAction(
        doseId: String,
        action: DoseAction,
        note: String? = null,
    ): AdherenceLog

    /** Saves routine first, then starts and polls the rescheduling agent. */
    suspend fun updateRoutine(routine: List<RoutineItem>): RoutineUpdateResult

    suspend fun submitHealthSurvey(
        mood: Int,
        symptoms: List<SurveySymptom>,
        surveyDate: LocalDate = LocalDate.now(),
    ): HealthSurvey

    suspend fun createSos(message: String?, shareLocation: Boolean): Alert

    suspend fun getMedicationDetail(medicationId: String): MedicationDetail

    suspend fun getCaregivers(): List<CaregiverLink>

    suspend fun createCaregiver(
        caregiverPhone: String,
        relationship: String?,
        channels: List<String> = listOf("APP_NOTIFICATION"),
    ): CaregiverLink

    suspend fun deleteCaregiver(caregiverLinkId: String): String

    suspend fun getAdherenceSummary(from: LocalDate, to: LocalDate): AdherenceSummary

    suspend fun getAdherenceLogs(
        from: LocalDate,
        to: LocalDate,
        page: Int = 1,
        size: Int = 20,
    ): PageResult<AdherenceLog>
}
