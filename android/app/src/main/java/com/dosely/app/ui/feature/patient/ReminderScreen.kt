package com.dosely.app.ui.feature.patient

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Medication
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import com.dosely.app.data.DoseToday
import com.dosely.app.ui.components.GhostButton
import com.dosely.app.ui.components.SuccessButton
import com.dosely.app.ui.components.WarningOutlineButton
import com.dosely.app.ui.theme.LocalDoselyColors

/**
 * Mirrors the interruptive push notification: patient sees this after
 * tapping an upcoming dose. In production it's triggered by the reminder
 * worker, not in-app navigation — see FR-3.1.
 */
@Composable
fun ReminderScreen(
    dose: DoseToday?,
    onAction: (doseId: String, action: String) -> Unit,
    onDone: () -> Unit,
) {
    val extras = LocalDoselyColors.current

    if (dose == null) {
        Column(
            modifier = Modifier.fillMaxSize().padding(28.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.Center,
        ) {
            Text(
                "Không tìm thấy cữ thuốc này. Lịch có thể vừa được cập nhật.",
                style = MaterialTheme.typography.bodyLarge,
                textAlign = TextAlign.Center,
            )
            GhostButton(
                "Quay lại lịch hôm nay",
                onClick = onDone,
                modifier = Modifier.fillMaxWidth().padding(top = 20.dp),
            )
        }
        return
    }

    val currentDose = dose
    val isLocked = currentDose.status == com.dosely.app.data.DoseStatus.LOCKED

    Column(
        modifier = Modifier.fillMaxSize().padding(horizontal = 28.dp, vertical = 36.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.SpaceBetween,
    ) {
        Column(horizontalAlignment = Alignment.CenterHorizontally) {
            Card(
                shape = CircleShape,
                colors = CardDefaults.cardColors(containerColor = extras.primaryTint),
                modifier = Modifier.size(84.dp).padding(bottom = 18.dp),
            ) {
                Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                    Icon(Icons.Filled.Medication, contentDescription = null, tint = MaterialTheme.colorScheme.primary, modifier = Modifier.size(38.dp))
                }
            }
            Text(
                "ĐẾN GIỜ UỐNG THUỐC",
                style = MaterialTheme.typography.labelMedium,
                color = extras.inkMuted,
            )
            Text(
                currentDose.medicationName,
                style = MaterialTheme.typography.headlineMedium,
                textAlign = TextAlign.Center,
                modifier = Modifier.padding(top = 10.dp),
            )
            Text(
                currentDose.doseLabel,
                style = MaterialTheme.typography.bodyLarge,
                color = extras.inkMuted,
                textAlign = TextAlign.Center,
            )
            Text(
                currentDose.time,
                style = MaterialTheme.typography.titleMedium,
                color = MaterialTheme.colorScheme.primary,
                modifier = Modifier.padding(top = 10.dp),
            )
        }

        Column(
            modifier = Modifier.fillMaxWidth(),
            verticalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            if (isLocked) {
                Text(
                    "Chưa đến giờ uống thuốc. Bạn có thể xác nhận khi đến giờ ${currentDose.time}.",
                    style = MaterialTheme.typography.bodyMedium,
                    color = extras.inkMuted,
                    textAlign = TextAlign.Center,
                    modifier = Modifier.fillMaxWidth(),
                )
                GhostButton("Quay lại lịch hôm nay", onClick = onDone, modifier = Modifier.fillMaxWidth())
            } else {
                SuccessButton(
                    "✓  Đã uống",
                    onClick = { onAction(currentDose.id, "TAKEN"); onDone() },
                    modifier = Modifier.fillMaxWidth(),
                )
                WarningOutlineButton(
                    "⏰  Uống muộn",
                    onClick = { onAction(currentDose.id, "LATE"); onDone() },
                    modifier = Modifier.fillMaxWidth(),
                )
                WarningOutlineButton(
                    "Nhắc lại sau",
                    onClick = { onAction(currentDose.id, "SNOOZE"); onDone() },
                    modifier = Modifier.fillMaxWidth(),
                )
                GhostButton(
                    "Bỏ qua",
                    onClick = { onAction(currentDose.id, "SKIPPED"); onDone() },
                    modifier = Modifier.fillMaxWidth(),
                )
            }
            Text(
                "Xác nhận trong vòng 60 phút để không bị tính là bỏ thuốc",
                style = MaterialTheme.typography.labelSmall,
                color = extras.inkMuted,
                textAlign = TextAlign.Center,
                modifier = Modifier.fillMaxWidth().padding(top = 6.dp),
            )
        }
    }
}

@com.dosely.app.ui.preview.DoselyScreenPreview
@Composable
private fun ReminderScreenPreview() = com.dosely.app.ui.preview.DoselyPreview {
    ReminderScreen(
        dose = com.dosely.app.ui.preview.previewDoses[1],
        onAction = { _, _ -> },
        onDone = {},
    )
}
