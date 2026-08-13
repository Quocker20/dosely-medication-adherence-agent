package com.remindrx.app.data.remote

import okhttp3.MultipartBody
import okhttp3.RequestBody
import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.Header
import retrofit2.http.Multipart
import retrofit2.http.POST
import retrofit2.http.PUT
import retrofit2.http.Part
import retrofit2.http.Path
import retrofit2.http.Query

interface RemindRxApiService {

    @POST("auth/login")
    suspend fun login(@Body request: LoginRequestDto): ApiEnvelope<AuthTokenResponseDto>

    @POST("auth/change-password")
    suspend fun changePassword(
        @Header("Authorization") authorization: String,
        @Body request: ChangePasswordRequestDto,
    ): ApiEnvelope<Unit?>

    @GET("patients/{patientId}/routine")
    suspend fun getRoutine(@Path("patientId") patientId: String): ApiEnvelope<PatientRoutineResponseDto>

    @PUT("patients/{patientId}/routine")
    suspend fun updateRoutine(
        @Path("patientId") patientId: String,
        @Body request: UpdateRoutineRequestDto,
    ): ApiEnvelope<PatientRoutineResponseDto>

    @GET("patients/{patientId}/schedules")
    suspend fun getSchedule(
        @Path("patientId") patientId: String,
        @Query("date") date: String? = null,
    ): ApiEnvelope<ScheduleResponseDto>

    @GET("patients/{patientId}/prescriptions")
    suspend fun getPrescriptions(
        @Path("patientId") patientId: String,
        @Query("status") status: String = "APPROVED",
        @Query("page") page: Int = 1,
        @Query("size") size: Int = 50,
    ): ApiEnvelope<PageResponseDto<PrescriptionDto>>

    @POST("scheduled-doses/{scheduledDoseId}/actions")
    suspend fun recordDoseAction(
        @Path("scheduledDoseId") scheduledDoseId: String,
        @Header("Idempotency-Key") idempotencyKey: String,
        @Body request: RecordDoseActionRequestDto,
    ): ApiEnvelope<AdherenceLogDto>

    @GET("patients/{patientId}/adherence")
    suspend fun getAdherenceSummary(@Path("patientId") patientId: String): ApiEnvelope<AdherenceSummaryDto>

    @POST("patients/{patientId}/health-surveys")
    suspend fun submitHealthSurvey(
        @Path("patientId") patientId: String,
        @Body request: SubmitHealthSurveyRequestDto,
    ): ApiEnvelope<HealthSurveyDto>

    @POST("patients/{patientId}/sos")
    suspend fun triggerSos(
        @Path("patientId") patientId: String,
        @Header("Idempotency-Key") idempotencyKey: String,
        @Body request: TriggerSosRequestDto,
    ): ApiEnvelope<AlertDto>

    // /chat và /chat/voice trả model trần (không ApiEnvelope) — xem ChatDtos.kt
    @POST("chat")
    suspend fun sendChatMessage(@Body request: ChatRequestDto): ChatResponseDto

    @Multipart
    @POST("chat/voice")
    suspend fun sendVoiceChatMessage(
        @Part("patient_id") patientId: RequestBody,
        @Part audio: MultipartBody.Part,
    ): VoiceChatResponseDto
}
