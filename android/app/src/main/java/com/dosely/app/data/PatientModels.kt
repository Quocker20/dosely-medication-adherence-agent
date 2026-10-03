package com.dosely.app.data

import java.time.LocalDate

enum class DoseAction { TAKEN, LATE, SNOOZE, SKIPPED }

data class AdherenceLog(
    val id: String,
    val scheduledDoseId: String?,
    val patientId: String,
    val action: String,
    val performedAt: String,
    val actionSource: String,
    val payload: Map<String, Any?>,
    val idempotencyKey: String?,
)

data class AdherenceSummary(
    val patientId: String,
    val fromDate: LocalDate,
    val toDate: LocalDate,
    val adherenceRate: Float,
    val totalDoses: Int,
    val takenDoses: Int,
    val skippedDoses: Int,
    val missedDoses: Int,
)

enum class PatientSex(val wireValue: String, val displayLabel: String) {
    MALE("MALE", "Nam"),
    FEMALE("FEMALE", "Nữ"),
    OTHER("OTHER", "Khác"),
}

/** Hồ sơ bệnh nhân trả về sau khi onboarding (POST /patients/me/profile). */
data class PatientProfile(
    val userId: String,
    val phone: String,
    val name: String,
    val dob: LocalDate?,
    val sex: String?,
    val timezone: String,
    val emergencyNote: String?,
)

data class OnboardingResult(
    val profile: PatientProfile,
    val routine: List<RoutineItem>,
)

data class PageResult<T>(
    val content: List<T>,
    val page: Int,
    val size: Int,
    val totalElements: Int,
    val totalPages: Int,
    val isLast: Boolean,
)

enum class SurveySeverity { MILD, MODERATE, SEVERE }

enum class SymptomCode(val wireValue: String, val displayLabel: String) {
    DIZZINESS("DIZZINESS", "Chóng mặt"),
    NAUSEA("NAUSEA", "Buồn nôn"),
    HEADACHE("HEADACHE", "Đau đầu"),
    FATIGUE("FATIGUE", "Mệt mỏi"),
    /** symptom_code không bị DB constraint giới hạn — dùng cho triệu chứng bệnh nhân tự mô tả. */
    OTHER("OTHER", "Khác"),
    ;

    companion object {
        fun fromDisplayLabel(label: String): SymptomCode? =
            entries.firstOrNull { it.displayLabel.equals(label.trim(), ignoreCase = true) }
    }
}

data class SurveySymptom(
    val code: SymptomCode,
    val severity: SurveySeverity,
    val description: String? = code.displayLabel,
)

data class HealthSurvey(
    val id: String,
    val patientId: String,
    val surveyDate: LocalDate,
    val status: String,
    val submittedAt: String?,
)

data class Alert(
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

data class CaregiverLink(
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

data class AgentRunRequest(
    val agentRunId: String,
    val status: String,
    val message: String,
)

data class AgentRun(
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
) {
    val isTerminal: Boolean get() = status !in setOf("PENDING", "QUEUED", "RUNNING")
    val isSuccessful: Boolean get() = status == "COMPLETED"
}

data class AgentRunPollResult(
    val lastRun: AgentRun?,
    val timedOut: Boolean,
)

enum class ScheduleUpdateStatus { UPDATED, FAILED, TIMED_OUT, QUEUED_OFFLINE }

data class RoutineUpdateResult(
    val routine: List<RoutineItem>,
    val scheduleStatus: ScheduleUpdateStatus,
    val agentRun: AgentRun? = null,
    val errorMessage: String? = null,
)
