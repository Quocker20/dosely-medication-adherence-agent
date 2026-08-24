package com.remindrx.app.data.remote

import okhttp3.MultipartBody
import retrofit2.http.Body
import retrofit2.http.DELETE
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

    @POST("auth/refresh")
    suspend fun refreshToken(@Body request: RefreshTokenRequestDto): ApiEnvelope<AuthTokenResponseDto>

    @POST("auth/logout")
    suspend fun logout(@Body request: LogoutRequestDto): ApiEnvelope<Unit?>

    @POST("auth/change-password")
    suspend fun changePassword(
        @Header("Authorization") authorization: String,
        @Body request: ChangePasswordRequestDto,
    ): ApiEnvelope<Unit?>

    // Bệnh nhân tự onboarding lần đầu — server lấy patient_id từ token, không nhận từ body.
    @POST("patients/me/profile")
    suspend fun onboardPatient(
        @Body request: PatientOnboardingRequestDto,
    ): ApiEnvelope<PatientProfileDetailResponseDto>

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

    @GET("medications/{medicationId}")
    suspend fun getMedicationDetail(
        @Path("medicationId") medicationId: String,
    ): ApiEnvelope<MedicationDetailResponseDto>

    @GET("patients/{patientId}/caregivers")
    suspend fun getCaregivers(
        @Path("patientId") patientId: String,
    ): ApiEnvelope<List<CaregiverLinkDetailResponseDto>>

    @POST("patients/{patientId}/caregivers")
    suspend fun createCaregiver(
        @Path("patientId") patientId: String,
        @Body request: CreateCaregiverLinkRequestDto,
    ): ApiEnvelope<CaregiverLinkDetailResponseDto>

    @DELETE("patients/{patientId}/caregivers/{caregiverLinkId}")
    suspend fun deleteCaregiver(
        @Path("patientId") patientId: String,
        @Path("caregiverLinkId") caregiverLinkId: String,
    ): ApiEnvelope<MessageResponseDto>

    @POST("scheduled-doses/{scheduledDoseId}/actions")
    suspend fun recordDoseAction(
        @Path("scheduledDoseId") scheduledDoseId: String,
        @Header("Idempotency-Key") idempotencyKey: String,
        @Body request: RecordDoseActionRequestDto,
    ): ApiEnvelope<AdherenceLogDto>

    @GET("patients/{patientId}/adherence")
    suspend fun getAdherenceSummary(
        @Path("patientId") patientId: String,
        @Query("from") from: String,
        @Query("to") to: String,
    ): ApiEnvelope<AdherenceSummaryDto>

    @GET("patients/{patientId}/adherence/logs")
    suspend fun getAdherenceLogs(
        @Path("patientId") patientId: String,
        @Query("from") from: String,
        @Query("to") to: String,
        @Query("page") page: Int = 1,
        @Query("size") size: Int = 20,
    ): ApiEnvelope<PageResponseDto<AdherenceLogDto>>

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

    @POST("patients/{patientId}/schedules/reschedule")
    suspend fun reschedule(
        @Path("patientId") patientId: String,
        @Body request: RescheduleRequestDto,
    ): ApiEnvelope<AgentRunAsyncResponseDto>

    @GET("agent-runs/{agentRunId}")
    suspend fun getAgentRunStatus(
        @Path("agentRunId") agentRunId: String,
    ): ApiEnvelope<AgentRunStatusResponseDto>

    @POST("chat")
    suspend fun sendChatMessage(@Body request: ChatRequestDto): ApiEnvelope<ChatResponseDto>

    @Multipart
    @POST("chat/voice")
    suspend fun sendVoiceChatMessage(
        @Part audio: MultipartBody.Part,
    ): ApiEnvelope<VoiceChatResponseDto>

    @POST("auth/device-token")
    suspend fun registerDeviceToken(
        @Body request: DeviceTokenRequestDto,
    ): ApiEnvelope<Unit?>
}
