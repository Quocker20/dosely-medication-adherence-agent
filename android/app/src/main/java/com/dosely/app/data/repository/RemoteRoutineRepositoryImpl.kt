package com.dosely.app.data.repository

import com.google.gson.Gson
import com.dosely.app.data.AgentRun
import com.dosely.app.data.AgentRunPollResult
import com.dosely.app.data.AgentRunRequest
import com.dosely.app.data.RoutineItem
import com.dosely.app.data.RoutineUpdateResult
import com.dosely.app.data.ScheduleUpdateStatus
import com.dosely.app.data.local.dao.OutboxDao
import com.dosely.app.data.local.dao.PatientCacheDao
import com.dosely.app.data.local.entity.OutboxActionEntity
import com.dosely.app.data.local.entity.OutboxActionType
import com.dosely.app.data.local.entity.UpdateRoutinePayload
import com.dosely.app.data.mapper.toDomain
import com.dosely.app.data.mapper.toOutboxRoutinePayloads
import com.dosely.app.data.mapper.toRoutineEntities
import com.dosely.app.data.mapper.toRoutineItems
import com.dosely.app.data.mapper.toRoutineRequestDto
import com.dosely.app.data.remote.DoselyApiService
import com.dosely.app.data.remote.RescheduleRequestDto
import com.dosely.app.data.remote.requireData
import java.io.IOException
import java.util.UUID
import javax.inject.Inject
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.delay
import kotlinx.coroutines.withTimeoutOrNull

class RemoteRoutineRepositoryImpl @Inject constructor(
    private val api: DoselyApiService,
    private val sessionStore: SessionStore,
    private val patientCacheDao: PatientCacheDao,
    private val outboxDao: OutboxDao,
    private val outboxSyncScheduler: OutboxSyncScheduler,
    private val gson: Gson,
) : RoutineRepository {

    override suspend fun getRoutine(): List<RoutineItem> {
        val patientId = sessionStore.requirePatientId()
        val cached = patientCacheDao.getRoutine(patientId).toRoutineItems()
        return try {
            api.getRoutine(patientId)
                .requireData("Tải thói quen sinh hoạt")
                .toRoutineItems()
                .also { routine ->
                    patientCacheDao.replaceRoutine(patientId, routine.toRoutineEntities(patientId))
                }
        } catch (cancellation: CancellationException) {
            throw cancellation
        } catch (error: IOException) {
            cached.ifEmpty { throw error }
        }
    }

    override suspend fun updateRoutine(routine: List<RoutineItem>): List<RoutineItem> =
        saveRoutine(routine).routine

    override suspend fun requestReschedule(reason: String?): AgentRunRequest =
        api.reschedule(
            patientId = sessionStore.requirePatientId(),
            request = RescheduleRequestDto(reason = reason?.trim()?.takeIf(String::isNotEmpty)),
        ).requireData("Yêu cầu cập nhật lịch thuốc").toDomain()

    override suspend fun getAgentRunStatus(agentRunId: String): AgentRun =
        api.getAgentRunStatus(agentRunId)
            .requireData("Kiểm tra tiến độ cập nhật lịch thuốc")
            .toDomain()

    override suspend fun awaitAgentRun(
        agentRunId: String,
        pollIntervalMillis: Long,
        timeoutMillis: Long,
    ): AgentRunPollResult {
        require(pollIntervalMillis > 0) { "Khoảng poll phải lớn hơn 0 ms." }
        require(timeoutMillis > 0) { "Thời gian chờ phải lớn hơn 0 ms." }

        var latest: AgentRun? = null
        val terminal = withTimeoutOrNull(timeoutMillis) {
            var current = getAgentRunStatus(agentRunId)
            latest = current
            while (!current.isTerminal) {
                delay(pollIntervalMillis)
                current = getAgentRunStatus(agentRunId)
                latest = current
            }
            current
        }
        return AgentRunPollResult(lastRun = terminal ?: latest, timedOut = terminal == null)
    }

    override suspend fun updateRoutineAndReschedule(
        routine: List<RoutineItem>,
        reason: String?,
    ): RoutineUpdateResult {
        // Saving the routine is authoritative. Agent failures are returned as
        // status so callers never imply that the already-saved routine rolled back.
        val routineWrite = saveRoutine(routine)
        val savedRoutine = routineWrite.routine
        if (routineWrite.queuedOffline) {
            return RoutineUpdateResult(
                routine = savedRoutine,
                scheduleStatus = ScheduleUpdateStatus.QUEUED_OFFLINE,
                errorMessage = null,
            )
        }
        return try {
            val request = requestReschedule(reason)
            val poll = awaitAgentRun(request.agentRunId)
            when {
                poll.timedOut -> RoutineUpdateResult(
                    routine = savedRoutine,
                    scheduleStatus = ScheduleUpdateStatus.TIMED_OUT,
                    agentRun = poll.lastRun,
                    errorMessage = "Đã lưu thói quen nhưng lịch thuốc vẫn đang được cập nhật.",
                )
                poll.lastRun?.isSuccessful == true -> RoutineUpdateResult(
                    routine = savedRoutine,
                    scheduleStatus = ScheduleUpdateStatus.UPDATED,
                    agentRun = poll.lastRun,
                )
                else -> RoutineUpdateResult(
                    routine = savedRoutine,
                    scheduleStatus = ScheduleUpdateStatus.FAILED,
                    agentRun = poll.lastRun,
                    errorMessage = poll.lastRun?.errorCode?.let { code ->
                        "Đã lưu thói quen nhưng chưa cập nhật được lịch thuốc (mã: $code)."
                    } ?: "Đã lưu thói quen nhưng chưa cập nhật được lịch thuốc.",
                )
            }
        } catch (cancelled: CancellationException) {
            throw cancelled
        } catch (error: Exception) {
            RoutineUpdateResult(
                routine = savedRoutine,
                scheduleStatus = ScheduleUpdateStatus.FAILED,
                errorMessage = error.message
                    ?: "Đã lưu thói quen nhưng chưa cập nhật được lịch thuốc.",
            )
        }
    }

    private suspend fun saveRoutine(routine: List<RoutineItem>): RoutineWriteResult {
        val patientId = sessionStore.requirePatientId()
        return try {
            api.updateRoutine(patientId, routine.toRoutineRequestDto())
                .requireData("Lưu thói quen sinh hoạt")
                .toRoutineItems()
                .also { savedRoutine ->
                    patientCacheDao.replaceRoutine(patientId, savedRoutine.toRoutineEntities(patientId))
                }
                .let { RoutineWriteResult(routine = it, queuedOffline = false) }
        } catch (cancellation: CancellationException) {
            throw cancellation
        } catch (error: IOException) {
            patientCacheDao.replaceRoutine(patientId, routine.toRoutineEntities(patientId))
            outboxDao.enqueue(
                OutboxActionEntity(
                    id = UUID.randomUUID().toString(),
                    patientId = patientId,
                    actionType = OutboxActionType.UPDATE_ROUTINE,
                    payloadJson = gson.toJson(UpdateRoutinePayload(routine = routine.toOutboxRoutinePayloads())),
                    createdAt = System.currentTimeMillis(),
                ),
            )
            outboxSyncScheduler.scheduleSync()
            RoutineWriteResult(routine = routine, queuedOffline = true)
        }
    }

    private data class RoutineWriteResult(
        val routine: List<RoutineItem>,
        val queuedOffline: Boolean,
    )
}
