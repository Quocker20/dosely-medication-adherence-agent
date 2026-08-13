package com.remindrx.app.data.remote

// Khớp src/modules/patients/schemas.py — thời gian gửi/nhận dạng "HH:mm".

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

// Khớp src/modules/agents/schemas.py:ActiveScheduleResponse — doses là danh
// sách dict thô ở backend (schema.md §6.4); model hoá thành DTO cụ thể cho
// an toàn kiểu dữ liệu ở phía Android.
data class DoseDto(
    val scheduledDoseId: String,
    val medicationName: String,
    val currentScheduledAt: String,
    val status: String,
    val snoozeCount: Int? = null,
)

data class ScheduleResponseDto(
    val patientId: String,
    val date: String,
    val doses: List<DoseDto>,
)

// Khớp src/modules/prescriptions/schemas.py

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
    val startDate: String,
    val endDate: String?,
    val instructions: String?,
)

data class PrescriptionDto(
    val id: String,
    val patientId: String,
    val status: String,
    val diagnosisNote: String?,
    val approvedAt: String?,
    val createdAt: String,
    val items: List<PrescriptionItemDto> = emptyList(),
)

data class PageResponseDto<T>(
    val content: List<T>,
    val pageNo: Int,
    val pageSize: Int,
    val totalElements: Int,
    val totalPages: Int,
    val last: Boolean,
)

// Slice 7 (api-contract.md) — CHƯA có route thật trên backend (không module
// nào implement adherence/health-surveys/sos/alerts). Gọi theo đúng hợp đồng
// đã tài liệu hoá; sẽ 404 cho tới khi backend bổ sung, và lỗi đó đã được
// PatientViewModel bắt + hiển thị thông báo tiếng Việt (không crash app).

data class RecordDoseActionRequestDto(val action: String, val note: String? = null)

data class AdherenceLogDto(
    val id: String,
    val scheduledDoseId: String,
    val action: String,
    val note: String?,
    val loggedAt: String,
)

data class AdherenceSummaryDto(
    val patientId: String,
    val adherenceRate: Int,
)

data class SubmitHealthSurveyRequestDto(
    val mood: Int,
    val symptoms: List<String>,
    val severity: String,
)

data class HealthSurveyDto(
    val id: String,
    val patientId: String,
    val mood: Int,
    val symptoms: List<String>,
    val severity: String,
)

data class TriggerSosRequestDto(val note: String?, val shareLocation: Boolean)

data class AlertDto(
    val id: String,
    val patientId: String,
    val state: String,
)
