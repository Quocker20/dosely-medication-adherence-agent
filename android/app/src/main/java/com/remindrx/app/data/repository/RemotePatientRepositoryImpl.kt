package com.remindrx.app.data.repository

import com.remindrx.app.data.AdherenceLog
import com.remindrx.app.data.AdherenceSummary
import com.remindrx.app.data.Alert
import com.remindrx.app.data.CaregiverLink
import com.remindrx.app.data.DoseAction
import com.remindrx.app.data.DoseToday
import com.remindrx.app.data.HealthSurvey
import com.remindrx.app.data.MedicationDetail
import com.remindrx.app.data.OnboardingResult
import com.remindrx.app.data.PageResult
import com.remindrx.app.data.PatientSex
import com.remindrx.app.data.RoutineItem
import com.remindrx.app.data.RoutineUpdateResult
import com.remindrx.app.data.SurveySymptom
import com.remindrx.app.data.mapper.toAdherencePage
import com.remindrx.app.data.mapper.toDoseToday
import com.remindrx.app.data.mapper.toDomain
import com.remindrx.app.data.mapper.toMedications
import com.remindrx.app.data.mapper.toRequestDto
import com.remindrx.app.data.mapper.toRoutineRequestDto
import com.remindrx.app.data.mapper.toSosRequestDto
import com.remindrx.app.data.mapper.toSurveyRequestDto
import com.remindrx.app.data.remote.CreateCaregiverLinkRequestDto
import com.remindrx.app.data.remote.PatientOnboardingRequestDto
import com.remindrx.app.data.remote.RemindRxApiService
import com.remindrx.app.data.remote.requireData
import java.time.DayOfWeek
import java.time.LocalDate
import java.time.temporal.TemporalAdjusters
import java.util.UUID
import javax.inject.Inject
import kotlinx.coroutines.async
import kotlinx.coroutines.coroutineScope

class RemotePatientRepositoryImpl @Inject constructor(
    private val api: RemindRxApiService,
    private val sessionStore: SessionStore,
    private val routineRepository: RoutineRepository,
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

    override suspend fun loadHome(): PatientHome = coroutineScope {
        val patientId = sessionStore.requirePatientId()
        val today = LocalDate.now()
        val weekStart = today.with(TemporalAdjusters.previousOrSame(DayOfWeek.MONDAY))

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

    override suspend fun recordDoseAction(
        doseId: String,
        action: DoseAction,
        note: String?,
    ): AdherenceLog = api.recordDoseAction(
        scheduledDoseId = doseId,
        idempotencyKey = UUID.randomUUID().toString(),
        request = action.toRequestDto(note),
    ).requireData("Ghi nhận cữ thuốc").toDomain()

    override suspend fun updateRoutine(routine: List<RoutineItem>): RoutineUpdateResult =
        routineRepository.updateRoutineAndReschedule(routine)

    override suspend fun submitHealthSurvey(
        mood: Int,
        symptoms: List<SurveySymptom>,
        surveyDate: LocalDate,
    ): HealthSurvey {
        require(mood in 1..5) { "Mức tâm trạng phải từ 1 đến 5." }
        return api.submitHealthSurvey(
            patientId = sessionStore.requirePatientId(),
            request = symptoms.toSurveyRequestDto(mood = mood, surveyDate = surveyDate),
        ).requireData("Gửi khảo sát sức khỏe").toDomain()
    }

    override suspend fun createSos(message: String?, shareLocation: Boolean): Alert =
        api.triggerSos(
            patientId = sessionStore.requirePatientId(),
            idempotencyKey = UUID.randomUUID().toString(),
            request = toSosRequestDto(message, shareLocation),
        ).requireData("Gửi cảnh báo SOS").toDomain()

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
        return api.createCaregiver(
            patientId = sessionStore.requirePatientId(),
            request = CreateCaregiverLinkRequestDto(
                caregiverPhone = normalizedPhone,
                relationship = normalizedRelationship,
                channels = normalizedChannels,
            ),
        ).requireData("Thêm người thân").toDomain(caregiverPhone = normalizedPhone)
    }

    override suspend fun deleteCaregiver(caregiverLinkId: String): String =
        api.deleteCaregiver(
            patientId = sessionStore.requirePatientId(),
            caregiverLinkId = caregiverLinkId,
        ).requireData("Xóa liên kết người thân").message

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
}
