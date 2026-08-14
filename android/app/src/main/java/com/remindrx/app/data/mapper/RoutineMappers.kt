package com.remindrx.app.data.mapper

import com.remindrx.app.data.RoutineItem
import com.remindrx.app.data.remote.PatientRoutineResponseDto
import com.remindrx.app.data.remote.UpdateRoutineRequestDto

fun PatientRoutineResponseDto.toRoutineItems(): List<RoutineItem> = listOf(
    RoutineItem("wake_time", "Thức dậy", wakeTime?.take(5).orEmpty()),
    RoutineItem("breakfast_time", "Ăn sáng", breakfastTime?.take(5).orEmpty()),
    RoutineItem("lunch_time", "Ăn trưa", lunchTime?.take(5).orEmpty()),
    RoutineItem("dinner_time", "Ăn tối", dinnerTime?.take(5).orEmpty()),
    RoutineItem("sleep_time", "Đi ngủ", sleepTime?.take(5).orEmpty()),
)

fun List<RoutineItem>.toRoutineRequestDto(): UpdateRoutineRequestDto {
    fun requiredTime(key: String): String {
        val value = firstOrNull { it.key == key }?.time
            ?: throw IllegalArgumentException("Thiếu mốc thói quen: $key")
        require(value.matches(Regex("(?:[01]\\d|2[0-3]):[0-5]\\d"))) {
            "Giờ không hợp lệ cho $key; cần định dạng HH:mm."
        }
        return value
    }
    return UpdateRoutineRequestDto(
        wakeTime = requiredTime("wake_time"),
        breakfastTime = requiredTime("breakfast_time"),
        lunchTime = requiredTime("lunch_time"),
        dinnerTime = requiredTime("dinner_time"),
        sleepTime = requiredTime("sleep_time"),
    )
}
