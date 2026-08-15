package com.remindrx.app.ui.preview

import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.Surface
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.tooling.preview.Preview
import com.remindrx.app.data.ChatConversation
import com.remindrx.app.data.ChatMessage
import com.remindrx.app.data.ChatRole
import com.remindrx.app.data.DosePeriod
import com.remindrx.app.data.DoseStatus
import com.remindrx.app.data.DoseToday
import com.remindrx.app.data.MealRelation
import com.remindrx.app.data.Medication
import com.remindrx.app.data.RoutineItem
import com.remindrx.app.ui.feature.assistant.AssistantUiState
import com.remindrx.app.ui.feature.patient.AdherenceLogUi
import com.remindrx.app.ui.feature.patient.AdherenceSummaryUi
import com.remindrx.app.ui.feature.patient.CaregiverUi
import com.remindrx.app.ui.feature.patient.MedicationDetailUi
import com.remindrx.app.ui.theme.RemindRxTheme

/** One consistent Android Studio canvas for every user-facing screen. */
@Target(AnnotationTarget.FUNCTION)
@Retention(AnnotationRetention.BINARY)
@Preview(
    name = "Phone · Light",
    showBackground = true,
    widthDp = 390,
    heightDp = 844,
    locale = "vi",
)
internal annotation class RemindRxScreenPreview

@Composable
internal fun RemindRxPreview(content: @Composable () -> Unit) {
    RemindRxTheme(darkTheme = false) {
        Surface(modifier = Modifier.fillMaxSize(), content = content)
    }
}

internal val previewRoutine = listOf(
    RoutineItem("wake_time", "Thức dậy", "06:30"),
    RoutineItem("breakfast_time", "Ăn sáng", "07:00"),
    RoutineItem("lunch_time", "Ăn trưa", "11:30"),
    RoutineItem("dinner_time", "Ăn tối", "18:00"),
    RoutineItem("sleep_time", "Đi ngủ", "22:00"),
)

internal val previewDoses = listOf(
    DoseToday(
        id = "dose-morning",
        time = "07:00",
        medicationName = "Metformin",
        doseLabel = "500 mg",
        mealRelation = MealRelation.AFTER_MEAL,
        status = DoseStatus.TAKEN,
        period = DosePeriod.MORNING,
        medicationId = "med-metformin",
    ),
    DoseToday(
        id = "dose-noon",
        time = "12:00",
        medicationName = "Amlodipine",
        doseLabel = "5 mg",
        mealRelation = MealRelation.AFTER_MEAL,
        status = DoseStatus.UPCOMING,
        period = DosePeriod.NOON,
        medicationId = "med-amlodipine",
    ),
    DoseToday(
        id = "dose-evening",
        time = "18:30",
        medicationName = "Atorvastatin",
        doseLabel = "10 mg",
        mealRelation = MealRelation.WITH_MEAL,
        status = DoseStatus.LOCKED,
        period = DosePeriod.EVENING,
        medicationId = "med-atorvastatin",
    ),
)

internal val previewMedications = listOf(
    Medication(
        name = "Metformin",
        doseLabel = "500 mg",
        times = listOf("07:00", "18:30"),
        remainingDaysLabel = "Còn 24 ngày",
        medicationId = "med-metformin",
        doseUnit = "mg",
        morningDose = 500.0,
        eveningDose = 500.0,
        mealRelation = MealRelation.AFTER_MEAL,
        instructions = "Uống sau bữa ăn và không tự ý thay đổi liều.",
    ),
    Medication(
        name = "Amlodipine",
        doseLabel = "5 mg",
        times = listOf("12:00"),
        remainingDaysLabel = "Còn 18 ngày",
        medicationId = "med-amlodipine",
        doseUnit = "mg",
        noonDose = 5.0,
        mealRelation = MealRelation.AFTER_MEAL,
    ),
)

internal val previewMedicationDetail = MedicationDetailUi(
    id = "med-metformin",
    name = "Metformin",
    composition = "Metformin hydrochloride 500 mg",
    manufacturer = "RemindRx Pharma",
    uses = "Hỗ trợ kiểm soát đường huyết ở người bệnh đái tháo đường type 2.",
    sideEffects = "Có thể gây buồn nôn hoặc khó chịu đường tiêu hoá.",
    sourceName = "Dữ liệu thuốc nội bộ",
    isActive = true,
)

internal val previewCaregivers = listOf(
    CaregiverUi(
        linkId = "caregiver-1",
        relationship = "Con gái",
        phone = "090 123 4567",
        status = "ACTIVE",
        channels = listOf("APP_NOTIFICATION"),
    ),
    CaregiverUi(
        linkId = "caregiver-2",
        relationship = "Em trai",
        phone = "091 234 5678",
        status = "PENDING",
        channels = listOf("APP_NOTIFICATION"),
    ),
)

internal val previewAdherenceSummary = AdherenceSummaryUi(
    fromDateLabel = "10/08",
    toDateLabel = "16/08",
    adherenceRate = 83.3f,
    totalDoses = 12,
    takenDoses = 10,
    skippedDoses = 1,
    missedDoses = 1,
)

internal val previewAdherenceLogs = listOf(
    AdherenceLogUi(
        id = "log-1",
        action = "TAKEN",
        performedAtLabel = "Hôm nay, 07:04",
        takenLate = true,
        note = "Uống sau bữa sáng.",
    ),
    AdherenceLogUi(
        id = "log-2",
        action = "SKIPPED",
        performedAtLabel = "Hôm qua, 18:30",
        note = "Bác sĩ dặn tạm ngưng một cữ.",
    ),
)

internal val previewMessages = listOf(
    ChatMessage(
        id = "message-1",
        role = ChatRole.ASSISTANT,
        content = "Chào bạn, mình có thể giúp kiểm tra lịch uống thuốc hôm nay.",
        time = "08:00",
    ),
    ChatMessage(
        id = "message-2",
        role = ChatRole.USER,
        content = "Liều tiếp theo của tôi là lúc nào?",
        time = "08:02",
    ),
    ChatMessage(
        id = "message-3",
        role = ChatRole.ASSISTANT,
        content = "Liều tiếp theo là Amlodipine 5 mg vào 12:00, sau bữa trưa.",
        time = "08:02",
    ),
)

internal val previewConversations = listOf(
    ChatConversation(
        id = "conversation-1",
        title = "Lịch uống thuốc hôm nay",
        updatedAt = "Hôm nay, 08:02",
        messages = previewMessages,
    ),
    ChatConversation(
        id = "conversation-2",
        title = "Tác dụng phụ của Metformin",
        updatedAt = "Hôm qua, 19:15",
        messages = listOf(
            ChatMessage(
                id = "message-4",
                role = ChatRole.ASSISTANT,
                content = "Nếu triệu chứng kéo dài hoặc nặng lên, hãy liên hệ bác sĩ.",
                time = "19:15",
            ),
        ),
    ),
)

internal val previewAssistantState = AssistantUiState(
    messages = previewMessages,
    conversations = previewConversations,
    isReplying = false,
    isRecording = false,
)
