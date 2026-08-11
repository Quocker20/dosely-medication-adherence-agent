package com.remindrx.app.ui.screens

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Alarm
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.Lightbulb
import androidx.compose.material.icons.filled.Medication
import androidx.compose.material.icons.filled.WarningAmber
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.remindrx.app.data.DosePeriod
import com.remindrx.app.data.DoseStatus
import com.remindrx.app.data.DoseToday
import com.remindrx.app.data.MealRelation
import com.remindrx.app.data.MockRepository
import com.remindrx.app.ui.components.AlertBellButton
import com.remindrx.app.ui.components.ChipTone
import com.remindrx.app.ui.components.PrimaryButton
import com.remindrx.app.ui.components.StatusChip
import com.remindrx.app.ui.components.TodayDoseCard
import com.remindrx.app.ui.theme.LocalRemindRxColors
import java.time.LocalDate
import java.time.format.DateTimeFormatter
import java.util.Locale

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun DashboardScreen(
    doses: List<DoseToday>,
    adherenceRate: Int,
    isLoading: Boolean,
    error: String?,
    onRetry: () -> Unit,
    onDoseAction: (doseId: String, action: String, note: String) -> Unit,
    onOpenDose: (String) -> Unit,
) {
    val extras = LocalRemindRxColors.current
    var skipTargetId by remember { mutableStateOf<String?>(null) }
    var skipReason by remember { mutableStateOf("") }

    val takenCount = doses.count { it.status == DoseStatus.TAKEN || it.status == DoseStatus.LATE }
    val nextDose = doses
        .filter { it.status in setOf(DoseStatus.UPCOMING, DoseStatus.SNOOZED, DoseStatus.LOCKED) }
        .minByOrNull { it.time }
    val insights = remember(doses, nextDose) { buildInsights(doses, nextDose) }
    val medicineCount = doses.map(DoseToday::medicationName).distinct().size

    LazyColumn(
        modifier = Modifier.fillMaxSize().padding(horizontal = 20.dp),
        contentPadding = PaddingValues(top = 18.dp, bottom = 24.dp),
    ) {
        item { DashboardHeader() }
        item { AdherenceCard(takenCount = takenCount, totalCount = doses.size, adherenceRate = adherenceRate) }

        if (isLoading) {
            item {
                Text(
                    "Đang đồng bộ lịch với bác sĩ…",
                    style = MaterialTheme.typography.bodyMedium,
                    color = extras.inkMuted,
                    modifier = Modifier.padding(vertical = 10.dp),
                )
            }
        }
        if (error != null) {
            item {
                Card(
                    shape = RoundedCornerShape(14.dp),
                    colors = CardDefaults.cardColors(containerColor = extras.dangerTint),
                    modifier = Modifier.fillMaxWidth().padding(vertical = 8.dp),
                ) {
                    Column(Modifier.padding(14.dp)) {
                        Text(error, style = MaterialTheme.typography.bodyMedium, color = extras.danger)
                        PrimaryButton("Thử đồng bộ lại", onClick = onRetry, modifier = Modifier.padding(top = 10.dp))
                    }
                }
            }
        }

        item { SectionTitle("Liều tiếp theo", modifier = Modifier.padding(top = 16.dp, bottom = 8.dp)) }
        item {
            if (nextDose != null) {
                NextDoseCard(
                    dose = nextDose,
                    onClick = { onOpenDose(nextDose.id) },
                    modifier = Modifier.padding(bottom = 8.dp),
                )
            } else {
                CompletedTodayCard(
                    hasScheduledDoses = doses.isNotEmpty(),
                    modifier = Modifier.padding(bottom = 8.dp),
                )
            }
        }

        item { SectionTitle("Cảnh báo & gợi ý", modifier = Modifier.padding(top = 12.dp, bottom = 8.dp)) }
        items(insights) { insight ->
            InsightCard(insight = insight, modifier = Modifier.padding(bottom = 8.dp))
        }

        item {
            Row(
                modifier = Modifier.fillMaxWidth().padding(top = 12.dp, bottom = 8.dp),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.Bottom,
            ) {
                SectionTitle("Thuốc hôm nay")
                Text(
                    "$medicineCount loại · ${doses.size} cữ",
                    style = MaterialTheme.typography.labelMedium,
                    color = extras.inkMuted,
                    fontWeight = FontWeight.Normal,
                )
            }
        }

        if (doses.isEmpty()) {
            item { EmptyScheduleCard() }
        } else {
            DosePeriod.entries.forEach { period ->
                val periodDoses = doses.filter { it.period == period }
                if (periodDoses.isNotEmpty()) {
                    item {
                        Text(
                            period.label,
                            style = MaterialTheme.typography.titleMedium,
                            modifier = Modifier.padding(top = 8.dp, bottom = 8.dp),
                        )
                    }
                    items(periodDoses, key = { it.id }) { dose ->
                        TodayDoseCard(
                            dose = dose,
                            onTaken = { onDoseAction(dose.id, "TAKEN", "") },
                            onLate = { onDoseAction(dose.id, "LATE", "") },
                            onSkip = { skipTargetId = dose.id },
                            onOpen = { onOpenDose(dose.id) },
                            modifier = Modifier.padding(bottom = 10.dp),
                        )
                    }
                }
            }
        }
    }

    val activeSkipId = skipTargetId
    if (activeSkipId != null) {
        ModalBottomSheet(onDismissRequest = { skipTargetId = null; skipReason = "" }) {
            Column(Modifier.padding(horizontal = 20.dp).padding(bottom = 28.dp)) {
                Text("Lý do bỏ qua cữ thuốc", style = MaterialTheme.typography.titleMedium)
                Text(
                    "Bác sĩ sẽ thấy lý do này trong nhật ký tuân thủ của bạn.",
                    style = MaterialTheme.typography.labelMedium,
                    color = extras.inkMuted,
                    fontWeight = FontWeight.Normal,
                    modifier = Modifier.padding(top = 4.dp, bottom = 14.dp),
                )
                OutlinedTextField(
                    value = skipReason,
                    onValueChange = { skipReason = it },
                    placeholder = { Text("VD: Hết thuốc, buồn nôn...") },
                    modifier = Modifier.fillMaxWidth(),
                )
                PrimaryButton(
                    "Xác nhận bỏ qua",
                    onClick = {
                        onDoseAction(activeSkipId, "SKIPPED", skipReason)
                        skipTargetId = null
                        skipReason = ""
                    },
                    modifier = Modifier.fillMaxWidth().padding(top = 16.dp),
                )
            }
        }
    }
}

@Composable
private fun SectionTitle(text: String, modifier: Modifier = Modifier) {
    Text(text, style = MaterialTheme.typography.titleMedium, modifier = modifier)
}

@Composable
private fun NextDoseCard(dose: DoseToday, onClick: () -> Unit, modifier: Modifier = Modifier) {
    val extras = LocalRemindRxColors.current
    Card(
        onClick = onClick,
        modifier = modifier.fillMaxWidth(),
        shape = RoundedCornerShape(18.dp),
        colors = CardDefaults.cardColors(containerColor = extras.primaryTint),
    ) {
        Column(Modifier.padding(18.dp)) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Icon(
                        Icons.Filled.Alarm,
                        contentDescription = null,
                        tint = MaterialTheme.colorScheme.primary,
                        modifier = Modifier.size(20.dp),
                    )
                    Text(
                        dose.time,
                        style = MaterialTheme.typography.headlineMedium,
                        color = MaterialTheme.colorScheme.primary,
                    )
                }
                when (dose.status) {
                    DoseStatus.SNOOZED -> StatusChip("Đã hoãn", ChipTone.WARNING)
                    DoseStatus.LOCKED -> StatusChip("Chưa đến giờ", ChipTone.MUTED)
                    else -> StatusChip("Sắp tới", ChipTone.NEUTRAL)
                }
            }
            Text(
                dose.medicationName,
                style = MaterialTheme.typography.titleLarge,
                modifier = Modifier.padding(top = 12.dp),
            )
            Text(
                listOf(dose.doseLabel, dose.mealRelation.label()).filter(String::isNotBlank).joinToString(" · "),
                style = MaterialTheme.typography.bodyMedium,
                color = extras.inkMuted,
                modifier = Modifier.padding(top = 3.dp),
            )
            Text(
                "Chạm để xem chi tiết",
                style = MaterialTheme.typography.labelMedium,
                color = MaterialTheme.colorScheme.primary,
                modifier = Modifier.padding(top = 12.dp),
            )
        }
    }
}

@Composable
private fun CompletedTodayCard(hasScheduledDoses: Boolean, modifier: Modifier = Modifier) {
    val extras = LocalRemindRxColors.current
    Card(
        modifier = modifier.fillMaxWidth(),
        shape = RoundedCornerShape(16.dp),
        colors = CardDefaults.cardColors(containerColor = extras.successTint),
    ) {
        Row(
            modifier = Modifier.padding(16.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Icon(Icons.Filled.CheckCircle, contentDescription = null, tint = extras.success)
            Column {
                Text(
                    if (hasScheduledDoses) "Đã hoàn thành lịch hôm nay" else "Chưa có liều tiếp theo",
                    style = MaterialTheme.typography.titleMedium,
                )
                Text(
                    if (hasScheduledDoses) {
                        "Không còn liều thuốc nào đang chờ."
                    } else {
                        "Lịch uống thuốc hôm nay đang trống."
                    },
                    style = MaterialTheme.typography.bodyMedium,
                    color = extras.inkMuted,
                )
            }
        }
    }
}

@Composable
private fun InsightCard(insight: DashboardInsight, modifier: Modifier = Modifier) {
    val extras = LocalRemindRxColors.current
    val (foreground, background, icon) = when (insight.tone) {
        InsightTone.DANGER -> Triple(extras.danger, extras.dangerTint, Icons.Filled.WarningAmber)
        InsightTone.WARNING -> Triple(extras.warning, extras.warningTint, Icons.Filled.Alarm)
        InsightTone.INFO -> Triple(MaterialTheme.colorScheme.primary, extras.primaryTint, Icons.Filled.Lightbulb)
        InsightTone.SUCCESS -> Triple(extras.success, extras.successTint, Icons.Filled.CheckCircle)
    }
    Card(
        modifier = modifier.fillMaxWidth(),
        shape = RoundedCornerShape(14.dp),
        colors = CardDefaults.cardColors(containerColor = background),
    ) {
        Row(
            modifier = Modifier.padding(14.dp),
            verticalAlignment = Alignment.Top,
            horizontalArrangement = Arrangement.spacedBy(11.dp),
        ) {
            Icon(icon, contentDescription = null, tint = foreground, modifier = Modifier.size(21.dp))
            Column(Modifier.weight(1f)) {
                Text(insight.title, style = MaterialTheme.typography.labelLarge, color = foreground)
                Text(
                    insight.message,
                    style = MaterialTheme.typography.labelMedium,
                    color = extras.inkMuted,
                    fontWeight = FontWeight.Normal,
                    modifier = Modifier.padding(top = 3.dp),
                )
            }
        }
    }
}

@Composable
private fun EmptyScheduleCard() {
    val extras = LocalRemindRxColors.current
    Card(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(16.dp),
        colors = CardDefaults.cardColors(containerColor = extras.surfaceAlt),
    ) {
        Row(
            modifier = Modifier.padding(16.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Icon(Icons.Filled.Medication, contentDescription = null, tint = extras.inkMuted)
            Text("Hôm nay chưa có thuốc trong lịch.", style = MaterialTheme.typography.bodyMedium)
        }
    }
}

private enum class InsightTone { DANGER, WARNING, INFO, SUCCESS }

private data class DashboardInsight(
    val title: String,
    val message: String,
    val tone: InsightTone,
)

private fun buildInsights(doses: List<DoseToday>, nextDose: DoseToday?): List<DashboardInsight> {
    if (doses.isEmpty()) {
        return listOf(
            DashboardInsight(
                title = "Chưa có lịch uống thuốc",
                message = "Lịch sẽ xuất hiện sau khi bác sĩ duyệt đơn thuốc của bạn.",
                tone = InsightTone.INFO,
            ),
        )
    }

    val insights = mutableListOf<DashboardInsight>()
    val skippedCount = doses.count { it.status == DoseStatus.SKIPPED }
    val lateCount = doses.count { it.status == DoseStatus.LATE }
    val snoozedDose = doses.firstOrNull { it.status == DoseStatus.SNOOZED }

    if (skippedCount > 0) {
        insights += DashboardInsight(
            title = "$skippedCount cữ thuốc đã bị bỏ qua",
            message = "Nếu bạn hết thuốc hoặc cảm thấy khó chịu, hãy liên hệ bác sĩ để được hỗ trợ.",
            tone = InsightTone.DANGER,
        )
    }
    if (snoozedDose != null) {
        insights += DashboardInsight(
            title = "Đừng quên liều đang hoãn",
            message = "${snoozedDose.medicationName} đã hoãn ${snoozedDose.snoozeMinutes ?: 15} phút.",
            tone = InsightTone.WARNING,
        )
    } else if (lateCount > 0) {
        insights += DashboardInsight(
            title = "$lateCount cữ được uống muộn",
            message = "Cố gắng giữ giờ uống ổn định; không tự ý uống gấp đôi liều.",
            tone = InsightTone.WARNING,
        )
    }

    if (nextDose != null) {
        insights += DashboardInsight(
            title = "Gợi ý cho liều tiếp theo",
            message = nextDose.suggestion(),
            tone = InsightTone.INFO,
        )
    } else {
        insights += DashboardInsight(
            title = "Bạn đã xong lịch hôm nay",
            message = "Tiếp tục duy trì thói quen tốt và kiểm tra lịch ngày mai.",
            tone = InsightTone.SUCCESS,
        )
    }
    return insights
}

private fun DoseToday.suggestion(): String = when (mealRelation) {
    MealRelation.BEFORE_MEAL -> "Chuẩn bị $medicationName để uống trước bữa ăn theo hướng dẫn."
    MealRelation.AFTER_MEAL -> "Dùng $medicationName sau bữa ăn và uống cùng đủ nước."
    MealRelation.WITH_MEAL -> "Dùng $medicationName cùng bữa ăn theo chỉ định."
    MealRelation.NONE -> "Chuẩn bị sẵn $medicationName và một cốc nước trước $time."
}

private fun MealRelation.label(): String = when (this) {
    MealRelation.NONE -> ""
    MealRelation.BEFORE_MEAL -> "Trước ăn"
    MealRelation.AFTER_MEAL -> "Sau ăn"
    MealRelation.WITH_MEAL -> "Cùng bữa ăn"
}

@Composable
private fun DashboardHeader() {
    val extras = LocalRemindRxColors.current
    val today = remember {
        LocalDate.now()
            .format(DateTimeFormatter.ofPattern("EEEE, dd/MM/yyyy", Locale("vi", "VN")))
            .replaceFirstChar { it.titlecase(Locale("vi", "VN")) }
    }
    Row(
        modifier = Modifier.fillMaxWidth().padding(bottom = 16.dp),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.Top,
    ) {
        Column {
            Text("Chào bác ${MockRepository.PATIENT_NAME}", style = MaterialTheme.typography.titleLarge)
            Text(
                today,
                style = MaterialTheme.typography.labelMedium,
                color = extras.inkMuted,
                fontWeight = FontWeight.SemiBold,
                modifier = Modifier.padding(top = 2.dp),
            )
        }
        AlertBellButton(unreadCount = MockRepository.UNREAD_ALERTS_COUNT, onClick = {})
    }
}

@Composable
private fun AdherenceCard(takenCount: Int, totalCount: Int, adherenceRate: Int) {
    val primary = MaterialTheme.colorScheme.primary
    val primaryDark = MaterialTheme.colorScheme.secondary
    val percent = if (adherenceRate > 0) {
        adherenceRate
    } else if (totalCount == 0) {
        100
    } else {
        takenCount * 100 / totalCount
    }
    Card(
        shape = RoundedCornerShape(18.dp),
        colors = CardDefaults.cardColors(containerColor = Color.Transparent),
        modifier = Modifier.fillMaxWidth().padding(bottom = 8.dp),
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .background(Brush.linearGradient(listOf(primary, primaryDark)))
                .padding(18.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(16.dp),
        ) {
            Canvas(modifier = Modifier.size(62.dp)) {
                val stroke = Stroke(width = 5.dp.toPx())
                drawArc(
                    color = Color.White.copy(alpha = 0.28f),
                    startAngle = -90f,
                    sweepAngle = 360f,
                    useCenter = false,
                    style = stroke,
                    size = Size(size.width, size.height),
                )
                drawArc(
                    color = Color.White,
                    startAngle = -90f,
                    sweepAngle = 360f * (percent / 100f),
                    useCenter = false,
                    style = stroke,
                    size = Size(size.width, size.height),
                )
            }
            Column {
                Text("$percent%", style = MaterialTheme.typography.headlineMedium, color = Color.White)
                Text(
                    "Tuân thủ tuần này",
                    style = MaterialTheme.typography.labelMedium,
                    color = Color.White.copy(alpha = 0.85f),
                    fontWeight = FontWeight.Normal,
                )
                Card(
                    shape = RoundedCornerShape(999.dp),
                    colors = CardDefaults.cardColors(containerColor = Color.White.copy(alpha = 0.16f)),
                    modifier = Modifier.padding(top = 8.dp),
                ) {
                    Text(
                        "$takenCount/$totalCount cữ đã uống",
                        style = MaterialTheme.typography.labelSmall,
                        color = Color.White,
                        modifier = Modifier.padding(horizontal = 10.dp, vertical = 5.dp),
                    )
                }
            }
        }
    }
}
