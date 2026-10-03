package com.dosely.app.data.repository

import com.dosely.app.data.AdherenceLog
import com.dosely.app.data.AdherenceSummary
import com.dosely.app.data.Alert
import com.dosely.app.data.CaregiverLink
import com.dosely.app.data.DoseAction
import com.dosely.app.data.DoseToday
import com.dosely.app.data.HealthSurvey
import com.dosely.app.data.Medication
import com.dosely.app.data.MedicationDetail
import com.dosely.app.data.OnboardingResult
import com.dosely.app.data.PageResult
import com.dosely.app.data.PatientSex
import com.dosely.app.data.RoutineItem
import com.dosely.app.data.RoutineUpdateResult
import com.dosely.app.data.SurveySymptom
import java.time.LocalDate
import kotlin.math.roundToInt
import kotlinx.coroutines.flow.Flow

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

    fun observePendingSyncCount(): Flow<Int>

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
