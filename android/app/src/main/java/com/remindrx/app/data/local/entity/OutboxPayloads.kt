package com.remindrx.app.data.local.entity

data class OutboxRoutineItemPayload(
    val key: String,
    val label: String,
    val time: String,
)

data class OutboxSymptomPayload(
    val code: String,
    val severity: String,
    val description: String?,
)

data class RecordDoseActionPayload(
    val scheduledDoseId: String,
    val action: String,
    val note: String?,
)

data class SubmitSurveyPayload(
    val mood: Int,
    val symptoms: List<OutboxSymptomPayload>,
    val surveyDate: String,
)

data class UpdateRoutinePayload(
    val routine: List<OutboxRoutineItemPayload>,
)

data class CreateSosPayload(
    val message: String?,
    val shareLocation: Boolean,
)

data class CreateCaregiverPayload(
    val caregiverPhone: String,
    val relationship: String?,
    val channels: List<String>,
)

data class DeleteCaregiverPayload(
    val caregiverLinkId: String,
)
