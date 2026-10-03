package com.dosely.app.ui.feature.patient

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ChevronRight
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.dosely.app.data.Medication
import com.dosely.app.ui.components.ChipTone
import com.dosely.app.ui.components.GuardrailNote
import com.dosely.app.ui.components.DoselyPullRefresh
import com.dosely.app.ui.components.StatusChip
import com.dosely.app.ui.components.TimeChip
import com.dosely.app.ui.theme.LocalDoselyColors

@Composable
fun PrescriptionScreen(
    medications: List<Medication>,
    onOpenMedication: (Medication) -> Unit,
    isRefreshing: Boolean = false,
    onRefresh: () -> Unit = {},
) {
    DoselyPullRefresh(isRefreshing = isRefreshing, onRefresh = onRefresh) {
        LazyColumn(
            modifier = Modifier.fillMaxSize().padding(horizontal = 20.dp),
            contentPadding = PaddingValues(top = 18.dp, bottom = 24.dp),
        ) {
            item {
                Text("Danh sách thuốc", style = MaterialTheme.typography.headlineMedium, modifier = Modifier.padding(bottom = 12.dp))
            }

            if (medications.isEmpty()) {
                item {
                    Text(
                        "Chưa có thuốc trong đơn hiện tại.",
                        style = MaterialTheme.typography.bodyMedium,
                        color = LocalDoselyColors.current.inkMuted,
                        modifier = Modifier.fillMaxWidth().padding(vertical = 24.dp),
                    )
                }
            } else {
                items(medications) { med -> MedicationCard(med, onClick = { onOpenMedication(med) }) }
            }

            item {
                GuardrailNote(
                    "Chỉ bác sĩ có quyền thay đổi đơn thuốc. Bạn không thể tự chỉnh liều hoặc số cữ.",
                    modifier = Modifier.fillMaxWidth().padding(top = 4.dp),
                )
            }
        }
    }
}

@Composable
private fun MedicationCard(med: Medication, onClick: () -> Unit) {
    val extras = LocalDoselyColors.current
    Card(
        onClick = onClick,
        shape = RoundedCornerShape(16.dp),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
        border = androidx.compose.foundation.BorderStroke(1.dp, extras.border),
        modifier = Modifier.fillMaxWidth().padding(bottom = 12.dp),
    ) {
        Column(Modifier.padding(14.dp)) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
            ) {
                Column {
                    Text(med.name, style = MaterialTheme.typography.titleMedium)
                    Text(med.doseLabel, style = MaterialTheme.typography.labelMedium, color = extras.inkMuted, fontWeight = FontWeight.Normal)
                }
                StatusChip(med.remainingDaysLabel, ChipTone.NEUTRAL)
            }
            Row(
                modifier = Modifier.padding(top = 8.dp),
                horizontalArrangement = Arrangement.spacedBy(6.dp),
            ) {
                med.times.forEach { time -> TimeChip(time) }
            }
            Row(
                modifier = Modifier.fillMaxWidth().padding(top = 12.dp),
                horizontalArrangement = Arrangement.End,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(
                    "Xem chi tiết",
                    style = MaterialTheme.typography.labelMedium,
                    color = MaterialTheme.colorScheme.primary,
                )
                Icon(
                    Icons.Filled.ChevronRight,
                    contentDescription = null,
                    tint = MaterialTheme.colorScheme.primary,
                )
            }
        }
    }
}

@com.dosely.app.ui.preview.DoselyScreenPreview
@Composable
private fun PrescriptionScreenPreview() = com.dosely.app.ui.preview.DoselyPreview {
    PrescriptionScreen(
        medications = com.dosely.app.ui.preview.previewMedications,
        onOpenMedication = {},
    )
}
