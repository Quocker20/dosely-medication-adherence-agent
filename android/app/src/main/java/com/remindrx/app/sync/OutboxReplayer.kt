package com.remindrx.app.sync

import com.google.gson.Gson
import com.remindrx.app.data.DoseAction
import com.remindrx.app.data.RoutineItem
import com.remindrx.app.data.SurveySeverity
import com.remindrx.app.data.SurveySymptom
import com.remindrx.app.data.SymptomCode
import com.remindrx.app.data.local.dao.PatientCacheDao
import com.remindrx.app.data.local.entity.CreateCaregiverPayload
import com.remindrx.app.data.local.entity.CreateSosPayload
import com.remindrx.app.data.local.entity.DeleteCaregiverPayload
import com.remindrx.app.data.local.entity.OutboxActionEntity
import com.remindrx.app.data.local.entity.OutboxActionType
import com.remindrx.app.data.local.entity.RecordDoseActionPayload
import com.remindrx.app.data.local.entity.SubmitSurveyPayload
import com.remindrx.app.data.local.entity.UpdateRoutinePayload
import com.remindrx.app.data.mapper.toRequestDto
import com.remindrx.app.data.mapper.toRoutineEntities
import com.remindrx.app.data.mapper.toRoutineItems
import com.remindrx.app.data.mapper.toRoutineRequestDto
import com.remindrx.app.data.mapper.toSosRequestDto
import com.remindrx.app.data.mapper.toSurveyRequestDto
import com.remindrx.app.data.remote.CreateCaregiverLinkRequestDto
import com.remindrx.app.data.remote.RemindRxApiService
import com.remindrx.app.data.remote.RescheduleRequestDto
import com.remindrx.app.data.remote.requireData
import java.io.IOException
import java.time.LocalDate
import javax.inject.Inject
import kotlinx.coroutines.CancellationException
import retrofit2.HttpException

/** Outcome of replaying one outbox row against the backend. */
sealed interface ReplayOutcome {
    data object Synced : ReplayOutcome
    data object Retryable : ReplayOutcome
    data class Failed(val reason: String) : ReplayOutcome
}

/**
 * Pure replay logic for [OutboxSyncWorker] — no WorkManager/Context dependency, so it is
 * unit-testable the same way as RemotePatientRepositoryImplTest (MockWebServer + fake DAO).
 *
 * Follows docs/outbox-replay-contract.md: never replay across patients (caller passes the
 * current session's patientId explicitly rather than trusting the row), and the specific
 * per-action-type conflict-as-synced rules documented there.
 */
class OutboxReplayer @Inject constructor(
    private val api: RemindRxApiService,
    private val patientCacheDao: PatientCacheDao,
    private val gson: Gson,
) {
    suspend fun replay(patientId: String, row: OutboxActionEntity): ReplayOutcome {
        if (row.patientId != patientId) {
            // Safety rule from the contract: never replay a row for a different logged-in
            // patient. This can only happen if a device is shared across accounts and the
            // previous patient's outbox wasn't drained before switching — leave it PENDING,
            // it will be replayed once that patient is signed in again.
            return ReplayOutcome.Retryable
        }
        return try {
            when (row.actionType) {
                OutboxActionType.RECORD_DOSE_ACTION -> replayDoseAction(row)
                OutboxActionType.SUBMIT_SURVEY -> replaySurvey(patientId, row)
                OutboxActionType.UPDATE_ROUTINE -> replayRoutine(patientId, row)
                OutboxActionType.CREATE_SOS -> replaySos(patientId, row)
                OutboxActionType.CREATE_CAREGIVER -> replayCreateCaregiver(patientId, row)
                OutboxActionType.DELETE_CAREGIVER -> replayDeleteCaregiver(patientId, row)
            }
            ReplayOutcome.Synced
        } catch (cancellation: CancellationException) {
            throw cancellation
        } catch (io: IOException) {
            ReplayOutcome.Retryable
        } catch (http: HttpException) {
            conflictAsSynced(row.actionType, http.code()) ?: ReplayOutcome.Failed(
                http.response()?.errorBody()?.string() ?: "HTTP ${http.code()}",
            )
        } catch (other: Exception) {
            ReplayOutcome.Failed(other.message ?: other.javaClass.simpleName)
        }
    }

    /**
     * DELETE_CAREGIVER is the only unconditionally safe case: a 404 on retry just means the
     * link is already gone, there is no "different content" ambiguity for a delete.
     *
     * SUBMIT_SURVEY/CREATE_CAREGIVER also hit a DB-level uniqueness constraint on conflict,
     * but per docs/outbox-replay-contract.md that should only be treated as synced "when the
     * existing record is equivalent" — we have no cheap way to fetch-and-diff that from the
     * client, so a 409 there falls through to Failed instead of being silently assumed
     * synced. Failed keeps the row (and its payload) in outbox_actions for manual review
     * rather than deleting a local survey/caregiver-link that might legitimately differ from
     * whatever already exists server-side.
     */
    private fun conflictAsSynced(actionType: OutboxActionType, httpCode: Int): ReplayOutcome? =
        when (actionType) {
            OutboxActionType.DELETE_CAREGIVER -> if (httpCode == 404) ReplayOutcome.Synced else null
            else -> null
        }

    private suspend fun replayDoseAction(row: OutboxActionEntity) {
        val payload = gson.fromJson(row.payloadJson, RecordDoseActionPayload::class.java)
        val action = DoseAction.valueOf(payload.action)
        api.recordDoseAction(
            scheduledDoseId = payload.scheduledDoseId,
            idempotencyKey = row.id,
            request = action.toRequestDto(payload.note),
        ).requireData("Đồng bộ ghi nhận cữ thuốc")
        // Local cache already reflects this action optimistically from the moment it was
        // queued (see RemotePatientRepositoryImpl.recordDoseAction) — nothing left to update.
    }

    private suspend fun replaySurvey(patientId: String, row: OutboxActionEntity) {
        val payload = gson.fromJson(row.payloadJson, SubmitSurveyPayload::class.java)
        val symptoms = payload.symptoms.map { symptom ->
            SurveySymptom(
                code = SymptomCode.valueOf(symptom.code),
                severity = SurveySeverity.valueOf(symptom.severity),
                description = symptom.description,
            )
        }
        api.submitHealthSurvey(
            patientId = patientId,
            request = symptoms.toSurveyRequestDto(mood = payload.mood, surveyDate = LocalDate.parse(payload.surveyDate)),
        ).requireData("Đồng bộ khảo sát sức khỏe")
    }

    private suspend fun replayRoutine(patientId: String, row: OutboxActionEntity) {
        val payload = gson.fromJson(row.payloadJson, UpdateRoutinePayload::class.java)
        val routine = payload.routine.map { item -> RoutineItem(key = item.key, label = item.label, time = item.time) }
        val saved = api.updateRoutine(patientId, routine.toRoutineRequestDto())
            .requireData("Đồng bộ thói quen sinh hoạt")
            .toRoutineItems()
        patientCacheDao.replaceRoutine(patientId, saved.toRoutineEntities(patientId))
        // Contract: request reschedule after the routine lands, but don't block this worker
        // run waiting for the agent to finish — awaitAgentRun's polling belongs to the
        // foreground UX (RoutineRepository.updateRoutineAndReschedule), not a background sync.
        runCatching {
            api.reschedule(patientId, RescheduleRequestDto(reason = "Đồng bộ thói quen ngoại tuyến"))
        }
    }

    private suspend fun replaySos(patientId: String, row: OutboxActionEntity) {
        val payload = gson.fromJson(row.payloadJson, CreateSosPayload::class.java)
        api.triggerSos(
            patientId = patientId,
            idempotencyKey = row.id,
            request = toSosRequestDto(payload.message, payload.shareLocation),
        ).requireData("Đồng bộ cảnh báo SOS")
    }

    private suspend fun replayCreateCaregiver(patientId: String, row: OutboxActionEntity) {
        val payload = gson.fromJson(row.payloadJson, CreateCaregiverPayload::class.java)
        api.createCaregiver(
            patientId = patientId,
            request = CreateCaregiverLinkRequestDto(
                caregiverPhone = payload.caregiverPhone,
                relationship = payload.relationship,
                channels = payload.channels,
            ),
        ).requireData("Đồng bộ thêm người thân")
    }

    private suspend fun replayDeleteCaregiver(patientId: String, row: OutboxActionEntity) {
        val payload = gson.fromJson(row.payloadJson, DeleteCaregiverPayload::class.java)
        api.deleteCaregiver(patientId = patientId, caregiverLinkId = payload.caregiverLinkId)
            .requireData("Đồng bộ xóa người thân")
    }
}
