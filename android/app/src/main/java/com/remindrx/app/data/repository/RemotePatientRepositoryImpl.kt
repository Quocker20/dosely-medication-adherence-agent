package com.remindrx.app.data.repository

import com.google.gson.Gson
import com.remindrx.app.data.AdherenceLog
import com.remindrx.app.data.AdherenceSummary
import com.remindrx.app.data.Alert
import com.remindrx.app.data.CaregiverLink
import com.remindrx.app.data.DoseAction
import com.remindrx.app.data.DoseStatus
import com.remindrx.app.data.DoseToday
import com.remindrx.app.data.HealthSurvey
import com.remindrx.app.data.MedicationDetail
import com.remindrx.app.data.OnboardingResult
import com.remindrx.app.data.PageResult
import com.remindrx.app.data.PatientSex
import com.remindrx.app.data.RoutineItem
import com.remindrx.app.data.RoutineUpdateResult
import com.remindrx.app.data.SurveySymptom
import com.remindrx.app.data.local.dao.OutboxDao
import com.remindrx.app.data.local.dao.PatientCacheDao
import com.remindrx.app.data.local.entity.CreateCaregiverPayload
import com.remindrx.app.data.local.entity.CreateSosPayload
import com.remindrx.app.data.local.entity.DeleteCaregiverPayload
import com.remindrx.app.data.local.entity.OutboxActionEntity
import com.remindrx.app.data.local.entity.OutboxActionType
import com.remindrx.app.data.local.entity.RecordDoseActionPayload
import com.remindrx.app.data.local.entity.SubmitSurveyPayload
import com.remindrx.app.data.mapper.toAdherencePage
import com.remindrx.app.data.mapper.toDomain
import com.remindrx.app.data.mapper.toDoseEntities
import com.remindrx.app.data.mapper.toDoseToday
import com.remindrx.app.data.mapper.toDoseTodayItems
import com.remindrx.app.data.mapper.toEntity
import com.remindrx.app.data.mapper.toMedicationEntities
import com.remindrx.app.data.mapper.toMedicationItems
import com.remindrx.app.data.mapper.toMedications
import com.remindrx.app.data.mapper.toOutboxSymptomPayloads
import com.remindrx.app.data.mapper.toRequestDto
import com.remindrx.app.data.mapper.toRoutineEntities
import com.remindrx.app.data.mapper.toRoutineItems
import com.remindrx.app.data.mapper.toRoutineRequestDto
import com.remindrx.app.data.mapper.toSosRequestDto
import com.remindrx.app.data.mapper.toSurveyRequestDto
import com.remindrx.app.data.remote.CreateCaregiverLinkRequestDto
import com.remindrx.app.data.remote.PatientOnboardingRequestDto
import com.remindrx.app.data.remote.RemindRxApiService
import com.remindrx.app.data.remote.requireData
import java.io.IOException
import java.time.DayOfWeek
import java.time.LocalDate
import java.time.OffsetDateTime
import java.time.ZoneOffset
import java.time.temporal.TemporalAdjusters
import java.util.UUID
import javax.inject.Inject
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.async
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.flatMapLatest
import kotlinx.coroutines.flow.flowOf

class RemotePatientRepositoryImpl @Inject constructor(
    private val api: RemindRxApiService,
    private val sessionStore: SessionStore,
    private val routineRepository: RoutineRepository,
    private val patientCacheDao: PatientCacheDao,
    private val outboxDao: OutboxDao,
    private val outboxSyncScheduler: OutboxSyncScheduler,
    private val gson: Gson,
) : PatientRepository {

    override suspend fun getRoutine(): List<RoutineItem> = routineRepository.getRoutine()

    override suspend fun onboard(
        name: String,
        routine: List<RoutineItem>,
        dob: LocalDate?,
        sex: PatientSex?,
        emergencyNote: String?,
        timezone: String,
    ): OnboardingResult {
        val trimmedName = name.trim()
        require(trimmedName.isNotEmpty()) { "Tên bệnh nhân không được để trống." }

        return api.onboardPatient(
            PatientOnboardingRequestDto(
                name = trimmedName,
                dob = dob?.toString(),
                sex = sex?.wireValue,
                timezone = timezone,
                emergencyNote = emergencyNote?.trim()?.takeIf(String::isNotEmpty),
                routine = routine.toRoutineRequestDto(),
            ),
        ).requireData("Hoàn tất hồ sơ bệnh nhân").toDomain()
    }

    @OptIn(kotlinx.coroutines.ExperimentalCoroutinesApi::class)
    override fun observePendingSyncCount(): Flow<Int> =
        sessionStore.session.flatMapLatest { session ->
            session?.let { outboxDao.observePendingCount(it.patientId) } ?: flowOf(0)
        }

    override suspend fun loadHome(): PatientHome {
        val patientId = sessionStore.requirePatientId()
        val today = LocalDate.now()
        val weekStart = today.with(TemporalAdjusters.previousOrSame(DayOfWeek.MONDAY))
        val cachedHome = loadCachedHome(patientId, today, weekStart)
        return try {
            loadRemoteHome(patientId, today, weekStart).also { home ->
                patientCacheDao.replaceHomeCache(
                    patientId = patientId,
                    scheduleDate = today.toString(),
                    routine = home.routine.toRoutineEntities(patientId),
                    doses = home.doses.toDoseEntities(patientId, today),
                    medications = home.medications.toMedicationEntities(patientId, gson),
                    adherenceSummary = home.adherence.toEntity(patientId),
                )
            }
        } catch (cancellation: CancellationException) {
            throw cancellation
        } catch (error: IOException) {
            cachedHome
        }
    }

    private suspend fun loadRemoteHome(
        patientId: String,
        today: LocalDate,
        weekStart: LocalDate,
    ): PatientHome = coroutineScope {
        val routineDeferred = async { routineRepository.getRoutine() }
        val prescriptionsDeferred = async {
            api.getPrescriptions(patientId).requireData("Tải đơn thuốc").content
        }
        val scheduleDeferred = async {
            api.getSchedule(patientId, date = today.toString())
                .requireData("Tải lịch thuốc")
                .doses
        }
        val adherenceDeferred = async { getAdherenceSummary(weekStart, today) }

        val prescriptions = prescriptionsDeferred.await()
        val doses = scheduleDeferred.await().map { it.toDoseToday() }
        val timesByPrescriptionItem = doses
            .mapNotNull { dose -> dose.prescriptionItemId?.let { it to dose.time } }
            .groupBy(keySelector = { it.first }, valueTransform = { it.second })
            .mapValues { (_, times) -> times.distinct() }

        PatientHome(
            routine = routineDeferred.await(),
            doses = doses,
            medications = prescriptions.toMedications().map { medication ->
                medication.copy(
                    times = medication.prescriptionItemId
                        ?.let(timesByPrescriptionItem::get)
                        .orEmpty(),
                )
            },
            adherence = adherenceDeferred.await(),
        )
    }

    private suspend fun loadCachedHome(
        patientId: String,
        today: LocalDate,
        weekStart: LocalDate,
    ): PatientHome {
        val weekEnd = today
        return PatientHome(
            routine = patientCacheDao.getRoutine(patientId).toRoutineItems(),
            doses = patientCacheDao.getDoses(patientId, today.toString()).toDoseTodayItems(),
            medications = patientCacheDao.getMedications(patientId).toMedicationItems(gson),
            adherence = patientCacheDao.getAdherenceSummary(
                patientId = patientId,
                fromDate = weekStart.toString(),
                toDate = weekEnd.toString(),
            )?.toDomain() ?: AdherenceSummary(
                patientId = patientId,
                fromDate = weekStart,
                toDate = weekEnd,
                adherenceRate = 0f,
                totalDoses = 0,
                takenDoses = 0,
                skippedDoses = 0,
                missedDoses = 0,
            ),
        )
    }

    override suspend fun recordDoseAction(
        doseId: String,
        action: DoseAction,
        note: String?,
    ): AdherenceLog {
        val patientId = sessionStore.requirePatientId()
        val idempotencyKey = UUID.randomUUID().toString()
        val request = action.toRequestDto(note)
        return try {
            api.recordDoseAction(
                scheduledDoseId = doseId,
                idempotencyKey = idempotencyKey,
                request = request,
            ).requireData("Ghi nhận cữ thuốc").toDomain().also {
                patientCacheDao.updateDoseStatus(patientId, doseId, action.toDoseStatus())
            }
        } catch (cancellation: CancellationException) {
            throw cancellation
        } catch (error: IOException) {
            patientCacheDao.updateDoseStatus(patientId, doseId, action.toDoseStatus())
            enqueueOutbox(
                id = idempotencyKey,
                patientId = patientId,
                actionType = OutboxActionType.RECORD_DOSE_ACTION,
                payload = RecordDoseActionPayload(
                    scheduledDoseId = doseId,
                    action = action.name,
                    note = note?.trim()?.takeIf(String::isNotEmpty),
                ),
            )
            AdherenceLog(
                id = idempotencyKey,
                scheduledDoseId = doseId,
                patientId = patientId,
                action = action.name,
                performedAt = nowIso(),
                actionSource = "PATIENT_MOBILE_APP",
                payload = request.payload,
                idempotencyKey = idempotencyKey,
            )
        }
    }

    override suspend fun updateRoutine(routine: List<RoutineItem>): RoutineUpdateResult =
        routineRepository.updateRoutineAndReschedule(routine)

    override suspend fun submitHealthSurvey(
        mood: Int,
        symptoms: List<SurveySymptom>,
        surveyDate: LocalDate,
    ): HealthSurvey {
        require(mood in 1..5) { "Mức tâm trạng phải từ 1 đến 5." }
        val patientId = sessionStore.requirePatientId()
        return try {
            api.submitHealthSurvey(
                patientId = patientId,
                request = symptoms.toSurveyRequestDto(mood = mood, surveyDate = surveyDate),
            ).requireData("Gửi khảo sát sức khỏe").toDomain()
        } catch (cancellation: CancellationException) {
            throw cancellation
        } catch (error: IOException) {
            val id = UUID.randomUUID().toString()
            enqueueOutbox(
                id = id,
                patientId = patientId,
                actionType = OutboxActionType.SUBMIT_SURVEY,
                payload = SubmitSurveyPayload(
                    mood = mood,
                    symptoms = symptoms.toOutboxSymptomPayloads(),
                    surveyDate = surveyDate.toString(),
                ),
            )
            HealthSurvey(
                id = id,
                patientId = patientId,
                surveyDate = surveyDate,
                status = QUEUED_OFFLINE,
                submittedAt = null,
            )
        }
    }

    override suspend fun createSos(message: String?, shareLocation: Boolean): Alert {
        val patientId = sessionStore.requirePatientId()
        val idempotencyKey = UUID.randomUUID().toString()
        return try {
            api.triggerSos(
                patientId = patientId,
                idempotencyKey = idempotencyKey,
                request = toSosRequestDto(message, shareLocation),
            ).requireData("Gửi cảnh báo SOS").toDomain()
        } catch (cancellation: CancellationException) {
            throw cancellation
        } catch (error: IOException) {
            enqueueOutbox(
                id = idempotencyKey,
                patientId = patientId,
                actionType = OutboxActionType.CREATE_SOS,
                payload = CreateSosPayload(
                    message = message?.trim()?.takeIf(String::isNotEmpty),
                    shareLocation = shareLocation,
                ),
            )
            Alert(
                id = idempotencyKey,
                patientId = patientId,
                assignedDoctorId = null,
                triggeredByType = "PATIENT",
                alertType = "SOS",
                severity = "CRITICAL",
                status = QUEUED_OFFLINE,
                message = message,
                createdAt = nowIso(),
            )
        }
    }

    override suspend fun getMedicationDetail(medicationId: String): MedicationDetail =
        api.getMedicationDetail(medicationId)
            .requireData("Tải chi tiết thuốc")
            .toDomain()

    override suspend fun getCaregivers(): List<CaregiverLink> =
        api.getCaregivers(sessionStore.requirePatientId())
            .requireData("Tải danh sách người thân")
            .map { it.toDomain() }

    override suspend fun createCaregiver(
        caregiverPhone: String,
        relationship: String?,
        channels: List<String>,
    ): CaregiverLink {
        val normalizedPhone = caregiverPhone.filterNot(Char::isWhitespace)
        val normalizedRelationship = relationship?.trim()?.takeIf(String::isNotEmpty)
        val normalizedChannels = channels.map { it.trim() }.filter { it.isNotEmpty() }.distinct()
        require(normalizedPhone.matches(Regex("^\\+?[0-9]{9,15}$"))) {
            "Số điện thoại người thân phải có từ 9 đến 15 chữ số."
        }
        require(normalizedRelationship == null || normalizedRelationship.length <= 50) {
            "Mối quan hệ không được dài quá 50 ký tự."
        }
        require(normalizedChannels.isNotEmpty()) { "Cần chọn ít nhất một kênh thông báo." }
        val patientId = sessionStore.requirePatientId()
        val request = CreateCaregiverLinkRequestDto(
            caregiverPhone = normalizedPhone,
            relationship = normalizedRelationship,
            channels = normalizedChannels,
        )
        return try {
            api.createCaregiver(
                patientId = patientId,
                request = request,
            ).requireData("Thêm người thân").toDomain(caregiverPhone = normalizedPhone)
        } catch (cancellation: CancellationException) {
            throw cancellation
        } catch (error: IOException) {
            val id = UUID.randomUUID().toString()
            enqueueOutbox(
                id = id,
                patientId = patientId,
                actionType = OutboxActionType.CREATE_CAREGIVER,
                payload = CreateCaregiverPayload(
                    caregiverPhone = normalizedPhone,
                    relationship = normalizedRelationship,
                    channels = normalizedChannels,
                ),
            )
            CaregiverLink(
                id = id,
                patientId = patientId,
                caregiverUserId = "",
                relationship = normalizedRelationship,
                channels = normalizedChannels,
                status = QUEUED_OFFLINE,
                createdAt = nowIso(),
                temporaryPassword = null,
                caregiverPhone = normalizedPhone,
            )
        }
    }

    override suspend fun deleteCaregiver(caregiverLinkId: String): String {
        val patientId = sessionStore.requirePatientId()
        return try {
            api.deleteCaregiver(
                patientId = patientId,
                caregiverLinkId = caregiverLinkId,
            ).requireData("Xóa liên kết người thân").message
        } catch (cancellation: CancellationException) {
            throw cancellation
        } catch (error: IOException) {
            enqueueOutbox(
                id = UUID.randomUUID().toString(),
                patientId = patientId,
                actionType = OutboxActionType.DELETE_CAREGIVER,
                payload = DeleteCaregiverPayload(caregiverLinkId = caregiverLinkId),
            )
            "Đã lưu yêu cầu gỡ người chăm sóc trên máy, chờ đồng bộ."
        }
    }

    override suspend fun getAdherenceSummary(from: LocalDate, to: LocalDate): AdherenceSummary {
        requireDateRange(from, to)
        return api.getAdherenceSummary(
            patientId = sessionStore.requirePatientId(),
            from = from.toString(),
            to = to.toString(),
        ).requireData("Tải thống kê tuân thủ").toDomain()
    }

    override suspend fun getAdherenceLogs(
        from: LocalDate,
        to: LocalDate,
        page: Int,
        size: Int,
    ): PageResult<AdherenceLog> {
        requireDateRange(from, to)
        require(page in 1..1_000) { "Trang phải nằm trong khoảng 1..1000." }
        require(size in 1..100) { "Kích thước trang phải nằm trong khoảng 1..100." }
        return api.getAdherenceLogs(
            patientId = sessionStore.requirePatientId(),
            from = from.toString(),
            to = to.toString(),
            page = page,
            size = size,
        ).requireData("Tải lịch sử tuân thủ").toAdherencePage()
    }

    private fun requireDateRange(from: LocalDate, to: LocalDate) {
        require(!to.isBefore(from)) { "Ngày kết thúc không được trước ngày bắt đầu." }
    }

    private suspend fun enqueueOutbox(
        id: String,
        patientId: String,
        actionType: OutboxActionType,
        payload: Any,
    ) {
        outboxDao.enqueue(
            OutboxActionEntity(
                id = id,
                patientId = patientId,
                actionType = actionType,
                payloadJson = gson.toJson(payload),
                createdAt = System.currentTimeMillis(),
            ),
        )
        outboxSyncScheduler.scheduleSync()
    }

    private fun DoseAction.toDoseStatus(): DoseStatus = when (this) {
        DoseAction.TAKEN -> DoseStatus.TAKEN
        DoseAction.LATE -> DoseStatus.LATE
        DoseAction.SNOOZE -> DoseStatus.SNOOZED
        DoseAction.SKIPPED -> DoseStatus.SKIPPED
    }

    private fun nowIso(): String = OffsetDateTime.now(ZoneOffset.UTC).toString()

    private companion object {
        const val QUEUED_OFFLINE = "QUEUED_OFFLINE"
    }
}
