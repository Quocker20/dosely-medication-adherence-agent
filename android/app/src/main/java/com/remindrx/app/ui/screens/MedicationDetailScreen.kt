package com.remindrx.app.ui.screens

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material.icons.filled.MenuBook
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.remindrx.app.data.Medication
import com.remindrx.app.data.MockMedicationKnowledge
import com.remindrx.app.ui.components.ChipTone
import com.remindrx.app.ui.components.GuardrailNote
import com.remindrx.app.ui.components.StatusChip
import com.remindrx.app.ui.components.TimeChip
import com.remindrx.app.ui.theme.LocalRemindRxColors

@Composable
fun MedicationDetailScreen(medication: Medication?, onBack: () -> Unit) {
    val extras = LocalRemindRxColors.current

    if (medication == null) {
        Column(Modifier.fillMaxSize().padding(20.dp)) {
            IconButton(onClick = onBack) {
                Icon(Icons.Filled.ArrowBack, contentDescription = "Quay lại")
            }
            Text("Không tìm thấy thông tin thuốc.", style = MaterialTheme.typography.titleMedium)
        }
        return
    }

    val knowledge = remember(medication.name) { MockMedicationKnowledge.find(medication.name) }
    LazyColumn(
        modifier = Modifier.fillMaxSize().padding(horizontal = 20.dp),
        contentPadding = PaddingValues(top = 10.dp, bottom = 28.dp),
    ) {
        item {
            Row(verticalAlignment = Alignment.CenterVertically) {
                IconButton(onClick = onBack) {
                    Icon(Icons.Filled.ArrowBack, contentDescription = "Quay lại")
                }
                Text("Chi tiết thuốc", style = MaterialTheme.typography.headlineMedium)
            }
        }

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
                        Text(medication.name, style = MaterialTheme.typography.titleLarge)
                        StatusChip("RAG mock", ChipTone.NEUTRAL)
                    }
                    Text(
                        medication.doseLabel,
                        style = MaterialTheme.typography.bodyMedium,
                        color = extras.inkMuted,
                        modifier = Modifier.padding(top = 4.dp),
                    )
                    Row(
                        horizontalArrangement = Arrangement.spacedBy(6.dp),
                        modifier = Modifier.padding(top = 12.dp),
                    ) {
                        medication.times.forEach { TimeChip(it) }
                    }
                    Text(
                        medication.remainingDaysLabel,
                        style = MaterialTheme.typography.labelMedium,
                        color = MaterialTheme.colorScheme.primary,
                        modifier = Modifier.padding(top = 10.dp),
                    )
                }
            }
        }

        item { KnowledgeSection("Thuốc này dùng để làm gì?", knowledge.summary) }
        item { KnowledgeSection("Cách dùng tham khảo", knowledge.howToUse) }
        if (knowledge.commonEffects.isNotEmpty()) {
            item { BulletSection("Tác dụng phụ thường gặp", knowledge.commonEffects, warning = false) }
        }
        item { BulletSection("Lưu ý quan trọng", knowledge.importantWarnings, warning = true) }

        item {
            Card(
                modifier = Modifier.fillMaxWidth().padding(top = 4.dp, bottom = 14.dp),
                shape = RoundedCornerShape(14.dp),
                colors = CardDefaults.cardColors(containerColor = extras.surfaceAlt),
            ) {
                Column(Modifier.padding(14.dp)) {
                    Row(
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.spacedBy(8.dp),
                    ) {
                        Icon(Icons.Filled.MenuBook, contentDescription = null, tint = MaterialTheme.colorScheme.primary)
                        Text("Nguồn tham khảo", style = MaterialTheme.typography.titleMedium)
                    }
                    knowledge.sources.forEach { source ->
                        Text(
                            source.title,
                            style = MaterialTheme.typography.labelMedium,
                            modifier = Modifier.padding(top = 10.dp),
                        )
                        Text(
                            source.url,
                            style = MaterialTheme.typography.labelSmall,
                            color = extras.inkMuted,
                            fontWeight = FontWeight.Normal,
                        )
                    }
                }
            }
        }

        item {
            GuardrailNote(
                "Nội dung RAG hiện là dữ liệu tham khảo mock, không thay thế đơn thuốc hoặc tư vấn của bác sĩ/dược sĩ. Không tự thay đổi liều.",
                modifier = Modifier.fillMaxWidth(),
            )
        }
    }
}

@Composable
private fun KnowledgeSection(title: String, content: String) {
    val extras = LocalRemindRxColors.current
    Column(Modifier.padding(bottom = 16.dp)) {
        Text(title, style = MaterialTheme.typography.titleMedium)
        Text(
            content,
            style = MaterialTheme.typography.bodyMedium,
            color = extras.inkMuted,
            modifier = Modifier.padding(top = 5.dp),
        )
    }
}

@Composable
private fun BulletSection(title: String, items: List<String>, warning: Boolean) {
    val extras = LocalRemindRxColors.current
    Card(
        modifier = Modifier.fillMaxWidth().padding(bottom = 14.dp),
        shape = RoundedCornerShape(14.dp),
        colors = CardDefaults.cardColors(
            containerColor = if (warning) extras.warningTint else extras.surfaceAlt,
        ),
    ) {
        Column(Modifier.padding(14.dp)) {
            Text(
                title,
                style = MaterialTheme.typography.titleMedium,
                color = if (warning) extras.warning else MaterialTheme.colorScheme.onSurface,
            )
            items.forEach { item ->
                Text(
                    "• $item",
                    style = MaterialTheme.typography.bodyMedium,
                    color = extras.inkMuted,
                    modifier = Modifier.padding(top = 7.dp),
                )
            }
        }
    }
}
