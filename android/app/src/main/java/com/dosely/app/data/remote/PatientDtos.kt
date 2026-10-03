package com.dosely.app.data.remote

/**
 * Wire models for the patient-facing FastAPI routes.
 *
 * Gson's LOWER_CASE_WITH_UNDERSCORES policy converts these camelCase names to
 * the snake_case used by Pydantic. Map keys are deliberately written in their
 * wire form because Gson naming policies do not transform map keys.
 */

// Patients / routine

data class UpdateRoutineRequestDto(
    val wakeTime: String? = null,
    val breakfastTime: String? = null,
    val lunchTime: String? = null,
    val dinnerTime: String? = null,
    val sleepTime: String? = null,
)

data class PatientRoutineResponseDto(
    val id: String,
    val patientId: String,
    val wakeTime: String?,
    val breakfastTime: String?,
    val lunchTime: String?,
    val dinnerTime: String?,
    val sleepTime: String?,
    val updatedAt: String,
)

/**
 * Onboarding lần đầu của bệnh nhân (POST /patients/me/profile).
 * Bệnh nhân lấy từ token nên không có patientId trong body.
 * `sex` chỉ nhận MALE | FEMALE | OTHER; `dob` dạng YYYY-MM-DD.
 */
data class PatientOnboardingRequestDto(
    val name: String,
    val dob: String? = null,
    val sex: String? = null,
    val timezone: String = "Asia/Ho_Chi_Minh",
    val emergencyNote: String? = null,
    val routine: UpdateRoutineRequestDto,
)

data class PatientProfileDto(
    val userId: String,
    val phone: String,
    val role: String,
    val status: String,
    val name: String,
    val dob: String?,
    val sex: String?,
    val timezone: String,
    val privacyConsentStatus: String?,
    val emergencyNote: String?,
    val createdAt: String,
    val updatedAt: String,
)

data class PatientProfileDetailResponseDto(
    val profile: PatientProfileDto,
    val routine: PatientRoutineResponseDto,
)

// Schedules / agent runs

data class DoseDto(
    val scheduledDoseId: String,
    val prescriptionItemId: String,
    val medicationId: String?,
    val medicationName: String,
    val currentScheduledAt: String,
    // Nullable for schedules generated before backend migration 0011.
    val doseSlot: String?,
    val doseValue: Double?,
    val doseUnit: String?,
    val mealRelation: String?,
    val status: String,
    val snoozeCount: Int? = null,
)

data class ScheduleResponseDto(
    val patientId: String,
    val date: String,
    val timezone: String? = null,
    val doses: List<DoseDto> = emptyList(),
)

data class RescheduleRequestDto(val reason: String? = null)

data class AgentRunAsyncResponseDto(
    val agentRunId: String,
    val status: String,
    val message: String,
)

data class AgentRunStatusResponseDto(
    val id: String,
    val agentType: String,
    val patientId: String,
    val prescriptionId: String?,
    val triggerType: String,
    val graphVersion: String,
    val status: String,
    val latencyMs: Int?,
    val errorCode: String?,
    val generatedDoseCount: Int?,
    val createdAt: String,
)

// Prescriptions / medication catalog

data class PrescriptionItemDto(
    val id: String,
    val prescriptionId: String,
    val medicationId: String?,
    val displayName: String,
    val doseUnit: String,
    val morningDose: Double?,
    val noonDose: Double?,
    val eveningDose: Double?,
    val bedtimeDose: Double?,
    val route: String,
    val mealRelation: String?,
    val minimumIntervalMinutes: Int?,
    val startDate: String,
    val endDate: String?,
    val instructions: String?,
    val createdAt: String,
)

data class PrescriptionDto(
    val id: String,
    val patientId: String,
    val doctorId: String?,
    val status: String,
    val diagnosisNote: String?,
    val approvedAt: String?,
    val createdAt: String,
    val items: List<PrescriptionItemDto> = emptyList(),
)

data class MedicationDetailResponseDto(
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

data class PageResponseDto<T>(
    val content: List<T> = emptyList(),
    val pageNo: Int,
    val pageSize: Int,
    val totalElements: Int,
    val totalPages: Int,
    val last: Boolean,
)

// Caregivers

data class CreateCaregiverLinkRequestDto(
    val caregiverPhone: String,
    val relationship: String? = null,
)

data class CaregiverLinkDetailResponseDto(
    val id: String,
    val patientId: String,
    val phone: String,
    val relationship: String? = null,
    val linkCode: String? = null,
    val telegramDeepLink: String? = null,
    val status: String,
    val telegramBoundAt: String? = null,
    val lastMessageSentAt: String? = null,
    val createdAt: String,
)

data class MessageResponseDto(val message: String)

// Adherence

data class RecordDoseActionRequestDto(
    val action: String,
    val actionSource: String = "PATIENT_MOBILE_APP",
    val payload: Map<String, Any?> = emptyMap(),
)

data class AdherenceLogDto(
    val id: String,
    val scheduledDoseId: String?,
    val patientId: String,
    val action: String,
    val performedAt: String,
    val actionSource: String,
    val payload: Map<String, Any?> = emptyMap(),
    val idempotencyKey: String?,
)

data class AdherenceSummaryDto(
    val patientId: String,
    val fromDate: String,
    val toDate: String,
    val adherenceRate: Float,
    val totalDoses: Int,
    val takenDoses: Int,
    val skippedDoses: Int,
    val missedDoses: Int,
)

// Daily health survey

data class SymptomEntryDto(
    val symptomCode: String,
    val severity: String,
    val description: String? = null,
)

data class SubmitHealthSurveyRequestDto(
    val surveyDate: String,
    val answersJson: Map<String, Any?>,
    val symptoms: List<SymptomEntryDto> = emptyList(),
)

data class HealthSurveyDto(
    val id: String,
    val patientId: String,
    val surveyDate: String,
    val status: String,
    val submittedAt: String?,
)

// SOS

data class TriggerSosRequestDto(
    val message: String?,
    val metadata: Map<String, Any?> = emptyMap(),
)

data class AlertDto(
    val id: String,
    val patientId: String,
    val assignedDoctorId: String?,
    val triggeredByType: String,
    val alertType: String,
    val severity: String,
    val status: String,
    val message: String?,
    val createdAt: String,
)
