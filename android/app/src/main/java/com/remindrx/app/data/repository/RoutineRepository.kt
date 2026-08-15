package com.remindrx.app.data.repository

import com.remindrx.app.data.AgentRun
import com.remindrx.app.data.AgentRunPollResult
import com.remindrx.app.data.AgentRunRequest
import com.remindrx.app.data.RoutineItem
import com.remindrx.app.data.RoutineUpdateResult

interface RoutineRepository {
    suspend fun getRoutine(): List<RoutineItem>

    suspend fun updateRoutine(routine: List<RoutineItem>): List<RoutineItem>

    suspend fun requestReschedule(reason: String? = null): AgentRunRequest

    suspend fun getAgentRunStatus(agentRunId: String): AgentRun

    suspend fun awaitAgentRun(
        agentRunId: String,
        pollIntervalMillis: Long = 2_000,
        timeoutMillis: Long = 60_000,
    ): AgentRunPollResult

    suspend fun updateRoutineAndReschedule(
        routine: List<RoutineItem>,
        reason: String? = "Patient routine updated from Android app",
    ): RoutineUpdateResult
}
