package com.remindrx.app.ui.feature.patient

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.automirrored.filled.MenuBook
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.remindrx.app.data.Medication
import com.remindrx.app.ui.components.ChipTone
import com.remindrx.app.ui.components.GuardrailNote
import com.remindrx.app.ui.components.PrimaryButton
import com.remindrx.app.ui.components.RemindRxPullRefresh
import com.remindrx.app.ui.components.StatusChip
import com.remindrx.app.ui.components.TimeChip
import com.remindrx.app.ui.theme.LocalRemindRxColors

/** Presentation model mapped from GET /medications/{medication_id}. */
data class MedicationDetailUi(
    val id: String,
    val name: String,
    val composition: String? = null,
    val manufacturer: String? = null,
    val uses: String? = null,
    val sideEffects: String? = null,
    val imageUrl: String? = null,
    val sourceName: String,
    val isActive: Boolean,
)

@Composable
fun MedicationDetailScreen(
    medication: Medication?,
    detail: MedicationDetailUi? = null,
    isLoading: Boolean = false,
    error: String? = null,
    onRetry: () -> Unit = {},
    onRefresh: () -> Unit = onRetry,
    onBack: () -> Unit,
) {
    RemindRxPullRefresh(isRefreshing = isLoading, onRefresh = onRefresh) {
        Column(Modifier.fillMaxSize()) {
            MedicationDetailHeader(onBack)

            when {
                isLoading -> Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                    CircularProgressIndicator()
                }

                error != null -> MedicationDetailError(error, onRetry)

                detail == null -> Box(
                    modifier = Modifier.fillMaxSize().padding(20.dp),
                    contentAlignment = Alignment.Center,
                ) {
                    Text("Không tìm thấy thông tin thuốc.", style = MaterialTheme.typography.titleMedium)
                }

                else -> MedicationDetailContent(medication = medication, detail = detail)
            }
        }
    }
}

@Composable
private fun MedicationDetailHeader(onBack: () -> Unit) {
    Row(
        modifier = Modifier.fillMaxWidth().padding(horizontal = 8.dp, vertical = 10.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        IconButton(onClick = onBack) {
            Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Quay lại")
        }
        Text("Chi tiết thuốc", style = MaterialTheme.typography.headlineMedium)
    }
}

@Composable
private fun MedicationDetailError(message: String, onRetry: () -> Unit) {
    val extras = LocalRemindRxColors.current
    Column(
        modifier = Modifier.fillMaxSize().padding(24.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center,
    ) {
        Text(message, style = MaterialTheme.typography.bodyMedium, color = extras.danger)
        PrimaryButton(
            text = "Thử lại",
            onClick = onRetry,
            modifier = Modifier.padding(top = 14.dp),
        )
    }
}

@Composable
private fun MedicationDetailContent(medication: Medication?, detail: MedicationDetailUi) {
    val extras = LocalRemindRxColors.current
    LazyColumn(
        modifier = Modifier.fillMaxSize().padding(horizontal = 20.dp),
        contentPadding = PaddingValues(bottom = 28.dp),
    ) {
        item {
            Card(
                modifier = Modifier.fillMaxWidth().padding(top = 8.dp, bottom = 14.dp),
                shape = RoundedCornerShape(18.dp),
                colors = CardDefaults.cardColors(containerColor = extras.primaryTint),
            ) {
                Column(Modifier.padding(18.dp)) {
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Text(detail.name, style = MaterialTheme.typography.titleLarge, modifier = Modifier.weight(1f))
                        StatusChip(
                            text = if (detail.isActive) "Đang sử dụng" else "Ngừng sử dụng",
                            tone = if (detail.isActive) ChipTone.SUCCESS else ChipTone.MUTED,
                        )
                    }
                    detail.composition?.takeIf(String::isNotBlank)?.let {
                        LabeledValue("Thành phần", it)
                    }
                    detail.manufacturer?.takeIf(String::isNotBlank)?.let {
                        LabeledValue("Nhà sản xuất", it)
                    }
                }
            }
        }

        medication?.let { prescriptionMedication ->
            item {
                Card(
                    modifier = Modifier.fillMaxWidth().padding(bottom = 16.dp),
                    shape = RoundedCornerShape(14.dp),
                    colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
                    border = androidx.compose.foundation.BorderStroke(1.dp, extras.border),
                ) {
                    Column(Modifier.padding(14.dp)) {
                        Text("Theo đơn thuốc của bạn", style = MaterialTheme.typography.titleMedium)
                        Text(
                            prescriptionMedication.doseLabel,
                            style = MaterialTheme.typography.bodyMedium,
                            color = extras.inkMuted,
                            modifier = Modifier.padding(top = 5.dp),
                        )
                        if (prescriptionMedication.times.isNotEmpty()) {
                            Row(
                                horizontalArrangement = Arrangement.spacedBy(6.dp),
                                modifier = Modifier.padding(top = 10.dp),
                            ) {
                                prescriptionMedication.times.forEach { TimeChip(it) }
                            }
                        }
                        Text(
                            prescriptionMedication.remainingDaysLabel,
                            style = MaterialTheme.typography.labelMedium,
                            color = MaterialTheme.colorScheme.primary,
                            modifier = Modifier.padding(top = 10.dp),
                        )
                    }
                }
            }
        }

        detail.uses?.takeIf(String::isNotBlank)?.let { uses ->
            item { KnowledgeSection("Thuốc này dùng để làm gì?", uses) }
        }
        detail.sideEffects?.takeIf(String::isNotBlank)?.let { sideEffects ->
            item { KnowledgeSection("Tác dụng phụ có thể gặp", sideEffects, warning = true) }
        }

        item {
            GuardrailNote(
                "Thông tin thuốc chỉ dùng để tham khảo, không thay thế đơn thuốc hoặc tư vấn của bác sĩ/dược sĩ. Không tự thay đổi liều.",
                modifier = Modifier.fillMaxWidth(),
            )
        }
    }
}

@Composable
private fun LabeledValue(label: String, value: String) {
    val extras = LocalRemindRxColors.current
    Text(label, style = MaterialTheme.typography.labelMedium, color = extras.inkMuted, modifier = Modifier.padding(top = 10.dp))
    Text(value, style = MaterialTheme.typography.bodyMedium, modifier = Modifier.padding(top = 2.dp))
}

@Composable
private fun KnowledgeSection(title: String, content: String, warning: Boolean = false) {
    val extras = LocalRemindRxColors.current
    Card(
        modifier = Modifier.fillMaxWidth().padding(bottom = 14.dp),
        shape = RoundedCornerShape(14.dp),
        colors = CardDefaults.cardColors(containerColor = if (warning) extras.warningTint else extras.surfaceAlt),
    ) {
        Column(Modifier.padding(14.dp)) {
            Text(
                title,
                style = MaterialTheme.typography.titleMedium,
                color = if (warning) extras.warning else MaterialTheme.colorScheme.onSurface,
            )
            Text(
                content,
                style = MaterialTheme.typography.bodyMedium,
                color = extras.inkMuted,
                modifier = Modifier.padding(top = 7.dp),
            )
        }
    }
}

@com.remindrx.app.ui.preview.RemindRxScreenPreview
@Composable
private fun MedicationDetailScreenPreview() = com.remindrx.app.ui.preview.RemindRxPreview {
    MedicationDetailScreen(
        medication = com.remindrx.app.ui.preview.previewMedications.first(),
        detail = com.remindrx.app.ui.preview.previewMedicationDetail,
        onBack = {},
    )
}
