package com.remindrx.app.data.repository

import com.remindrx.app.data.RoutineItem
import com.remindrx.app.data.remote.PatientRoutineResponseDto
import com.remindrx.app.data.remote.RemindRxApiService
import com.remindrx.app.data.remote.UpdateRoutineRequestDto
import javax.inject.Inject

class RemoteRoutineRepositoryImpl @Inject constructor(
    private val api: RemindRxApiService,
    private val sessionStore: SessionStore,
) : RoutineRepository {

    override suspend fun getRoutine(): List<RoutineItem> {
        val dto = requireNotNull(api.getRoutine(sessionStore.requirePatientId()).data) {
            "Phản hồi thói quen sinh hoạt rỗng"
        }
        return dto.toRoutineItems()
    }

    override suspend fun updateRoutine(routine: List<RoutineItem>): List<RoutineItem> {
        val dto = requireNotNull(
            api.updateRoutine(sessionStore.requirePatientId(), routine.toRequest()).data,
        ) { "Phản hồi thói quen sinh hoạt rỗng" }
        return dto.toRoutineItems()
    }
}

// PatientViewModel.saveRoutine() yêu cầu đúng 5 mốc giờ — luôn trả đủ 5,
// dùng giờ mặc định hợp lý nếu backend chưa có giá trị (VD: chưa onboarding).
// pydantic `time` serialize ra "HH:MM:SS" nhưng SettingsScreen.isValidTime()
// chỉ chấp nhận đúng 5 ký tự "HH:mm" — phải cắt bớt giây trước khi đưa vào UI.
private fun PatientRoutineResponseDto.toRoutineItems(): List<RoutineItem> = listOf(
    RoutineItem("wake_time", "Thức dậy", (wakeTime ?: "06:30").take(5)),
    RoutineItem("breakfast_time", "Ăn sáng", (breakfastTime ?: "07:00").take(5)),
    RoutineItem("lunch_time", "Ăn trưa", (lunchTime ?: "11:30").take(5)),
    RoutineItem("dinner_time", "Ăn tối", (dinnerTime ?: "18:00").take(5)),
    RoutineItem("sleep_time", "Đi ngủ", (sleepTime ?: "22:00").take(5)),
)

private fun List<RoutineItem>.toRequest(): UpdateRoutineRequestDto {
    fun time(key: String) = firstOrNull { it.key == key }?.time
    return UpdateRoutineRequestDto(
        wakeTime = time("wake_time"),
        breakfastTime = time("breakfast_time"),
        lunchTime = time("lunch_time"),
        dinnerTime = time("dinner_time"),
        sleepTime = time("sleep_time"),
    )
}
