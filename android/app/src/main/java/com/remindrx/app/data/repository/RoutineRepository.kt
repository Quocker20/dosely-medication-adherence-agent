package com.remindrx.app.data.repository

import com.remindrx.app.data.RoutineItem

interface RoutineRepository {
    suspend fun getRoutine(): List<RoutineItem>
    suspend fun updateRoutine(routine: List<RoutineItem>): List<RoutineItem>
}
