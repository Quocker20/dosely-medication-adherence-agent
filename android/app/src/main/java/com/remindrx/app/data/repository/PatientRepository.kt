package com.remindrx.app.data.repository

import com.remindrx.app.data.DoseToday
import com.remindrx.app.data.Medication
import com.remindrx.app.data.RoutineItem

data class PatientHome(
    val routine: List<RoutineItem>,
    val doses: List<DoseToday>,
    val medications: List<Medication>,
    val adherenceRate: Int,
)

interface PatientRepository {
    suspend fun loadHome(): PatientHome
    suspend fun recordDoseAction(doseId: String, action: String, note: String)
    suspend fun updateRoutine(routine: List<RoutineItem>): List<RoutineItem>
    suspend fun submitHealthSurvey(mood: Int, symptoms: List<String>, severity: String)
    suspend fun createSos(note: String, shareLocation: Boolean)
}
