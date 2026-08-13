package com.remindrx.app.data

data class EmergencyContact(val name: String, val relation: String, val phone: String)

/**
 * Dữ liệu giả cho preview Compose và làm state khởi tạo trước khi
 * PatientRepository thật trả về (xem PatientUiState). Runtime luôn được
 * ghi đè bởi dữ liệu backend ngay khi PatientViewModel.refresh() hoàn tất.
 */
object MockRepository {
    const val PATIENT_NAME = "Trần Lan"
    const val PATIENT_PHONE = "0900000000"
    const val UNREAD_ALERTS_COUNT = 0
    const val DOCTOR_LINE = "Đơn thuốc đã được bác sĩ duyệt"
    const val DOCTOR_APPROVED_ON = "Cập nhật gần nhất hôm nay"

    val emergencyContact = EmergencyContact(name = "Chị Hoa", relation = "Con gái", phone = "0900000001")

    val symptomOptions = listOf("Không có", "Chóng mặt", "Buồn nôn", "Đau đầu", "Mệt mỏi")

    val routine: List<RoutineItem> = listOf(
        RoutineItem("wake_time", "Thức dậy", "06:30"),
        RoutineItem("breakfast_time", "Ăn sáng", "07:00"),
        RoutineItem("lunch_time", "Ăn trưa", "11:30"),
        RoutineItem("dinner_time", "Ăn tối", "18:00"),
        RoutineItem("sleep_time", "Đi ngủ", "22:00"),
    )

    val medications: List<Medication> = listOf(
        Medication("Metformin", "500mg", listOf("07:00", "18:00"), "Còn 12 ngày"),
        Medication("Losartan", "50mg", listOf("07:00"), "Còn 20 ngày"),
    )

    val todayDoses: List<DoseToday> = listOf(
        DoseToday(
            id = "mock-1",
            time = "07:00",
            medicationName = "Metformin",
            doseLabel = "500mg",
            mealRelation = MealRelation.WITH_MEAL,
            status = DoseStatus.UPCOMING,
            period = DosePeriod.MORNING,
        ),
        DoseToday(
            id = "mock-2",
            time = "18:00",
            medicationName = "Metformin",
            doseLabel = "500mg",
            mealRelation = MealRelation.WITH_MEAL,
            status = DoseStatus.LOCKED,
            period = DosePeriod.EVENING,
        ),
    )
}
