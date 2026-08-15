package com.remindrx.app.data.repository

import com.remindrx.app.data.AgentRun
import com.remindrx.app.data.AgentRunPollResult
import com.remindrx.app.data.AgentRunRequest
import com.remindrx.app.data.RoutineItem
import com.remindrx.app.data.RoutineUpdateResult
import com.remindrx.app.data.ScheduleUpdateStatus
import com.remindrx.app.data.mapper.toDomain
import com.remindrx.app.data.mapper.toRoutineItems
import com.remindrx.app.data.mapper.toRoutineRequestDto
import com.remindrx.app.data.remote.RemindRxApiService
import com.remindrx.app.data.remote.RescheduleRequestDto
import com.remindrx.app.data.remote.requireData
import java.util.concurrent.CancellationException
import javax.inject.Inject
import kotlinx.coroutines.delay
import kotlinx.coroutines.withTimeoutOrNull

class RemoteRoutineRepositoryImpl @Inject constructor(
    private val api: RemindRxApiService,
    private val sessionStore: SessionStore,
) : RoutineRepository {

    override suspend fun getRoutine(): List<RoutineItem> =
        api.getRoutine(sessionStore.requirePatientId())
            .requireData("Tải thói quen sinh hoạt")
            .toRoutineItems()

    override suspend fun updateRoutine(routine: List<RoutineItem>): List<RoutineItem> =
        api.updateRoutine(sessionStore.requirePatientId(), routine.toRoutineRequestDto())
            .requireData("Lưu thói quen sinh hoạt")
            .toRoutineItems()

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
        val savedRoutine = updateRoutine(routine)
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
}
