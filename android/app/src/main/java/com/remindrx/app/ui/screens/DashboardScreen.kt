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
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.getValue
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import com.remindrx.app.data.DosePeriod
import com.remindrx.app.data.DoseStatus
import com.remindrx.app.data.DoseToday
import com.remindrx.app.data.MockRepository
import com.remindrx.app.ui.components.AlertBellButton
import com.remindrx.app.ui.components.PrimaryButton
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
    val pendingCount = doses.count { it.status == DoseStatus.UPCOMING || it.status == DoseStatus.LOCKED }
    val allDone = pendingCount == 0

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

        if (allDone) {
            item { AllDoneState(modifier = Modifier.fillMaxWidth().padding(top = 24.dp)) }
        } else {
            DosePeriod.entries.forEach { period ->
                val periodDoses = doses.filter { it.period == period }
                if (periodDoses.isNotEmpty()) {
                    item {
                        Text(
                            period.label,
                            style = MaterialTheme.typography.titleMedium,
                            modifier = Modifier.padding(top = 14.dp, bottom = 8.dp),
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
    val percent = if (adherenceRate > 0) adherenceRate else if (totalCount == 0) 100 else (takenCount * 100 / totalCount)
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
                Text(
                    "$percent%",
                    style = MaterialTheme.typography.headlineMedium,
                    color = Color.White,
                )
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

@Composable
private fun AllDoneState(modifier: Modifier = Modifier) {
    val extras = LocalRemindRxColors.current
    Column(
        modifier = modifier.padding(vertical = 32.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Card(
            shape = CircleShape,
            colors = CardDefaults.cardColors(containerColor = extras.successTint),
            modifier = Modifier.size(96.dp),
        ) {
            Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                Icon(Icons.Filled.CheckCircle, contentDescription = null, tint = extras.success, modifier = Modifier.size(48.dp))
            }
        }
        Text(
            "Bạn đã hoàn thành lịch uống thuốc hôm nay!",
            style = MaterialTheme.typography.titleMedium,
            textAlign = TextAlign.Center,
            modifier = Modifier.padding(top = 18.dp),
        )
        Text(
            "Hẹn gặp lại bạn ở cữ thuốc tiếp theo.",
            style = MaterialTheme.typography.bodyMedium,
            color = extras.inkMuted,
            textAlign = TextAlign.Center,
            modifier = Modifier.padding(top = 6.dp),
        )
    }
}
