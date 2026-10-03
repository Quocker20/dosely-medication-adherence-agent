package com.dosely.app.ui.feature.patient

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.rememberScrollState
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import com.dosely.app.ui.components.PrimaryButton
import com.dosely.app.ui.theme.LocalDoselyColors

private enum class Severity(val label: String) { MILD("Nhẹ"), MODERATE("Vừa"), SEVERE("Nặng") }

private data class SymptomOption(val code: String, val label: String)

private val symptomOptions = listOf(
    SymptomOption("NONE", "Không có"),
    SymptomOption("DIZZINESS", "Chóng mặt"),
    SymptomOption("NAUSEA", "Buồn nôn"),
    SymptomOption("HEADACHE", "Đau đầu"),
    SymptomOption("FATIGUE", "Mệt mỏi"),
    SymptomOption("OTHER", "Khác"),
)

@OptIn(ExperimentalLayoutApi::class)
@Composable
fun SurveyScreen(
    isSubmitting: Boolean = false,
    isSubmitted: Boolean = false,
    error: String? = null,
    onInputChanged: () -> Unit = {},
    onSubmit: (mood: Int, symptomCode: String, severity: String, customDescription: String?) -> Unit,
) {
    val extras = LocalDoselyColors.current
    var mood by remember { mutableIntStateOf(3) }
    var selectedSymptom by remember { mutableStateOf(symptomOptions.first()) }
    var severity by remember { mutableStateOf(Severity.MILD) }
    var customDescription by remember { mutableStateOf("") }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(horizontal = 20.dp, vertical = 18.dp),
    ) {
        Text("Khảo sát cuối ngày", style = MaterialTheme.typography.headlineMedium)
        Text(
            "2 câu hỏi ngắn, giúp bác sĩ theo dõi từ xa.",
            style = MaterialTheme.typography.bodyMedium,
            color = extras.inkMuted,
            modifier = Modifier.padding(top = 4.dp, bottom = 18.dp),
        )

        Text("Hôm nay bạn cảm thấy thế nào?", style = MaterialTheme.typography.titleMedium, modifier = Modifier.padding(bottom = 10.dp))
        Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            (1..5).forEach { value ->
                MoodDot(value, picked = mood == value, modifier = Modifier.weight(1f)) {
                    mood = value
                    onInputChanged()
                }
            }
        }
        Row(modifier = Modifier.fillMaxWidth().padding(top = 6.dp, bottom = 22.dp), horizontalArrangement = Arrangement.SpaceBetween) {
            Text("Rất tệ", style = MaterialTheme.typography.labelSmall, color = extras.inkMuted)
            Text("Rất tốt", style = MaterialTheme.typography.labelSmall, color = extras.inkMuted)
        }

        Text("Có tác dụng phụ nào không?", style = MaterialTheme.typography.titleMedium, modifier = Modifier.padding(bottom = 10.dp))
        FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.padding(bottom = if (selectedSymptom.code == "OTHER") 10.dp else 22.dp)) {
            symptomOptions.forEach { symptom ->
                SymptomChip(symptom.label, picked = selectedSymptom == symptom) {
                    selectedSymptom = symptom
                    if (symptom.code == "NONE") severity = Severity.MILD
                    onInputChanged()
                }
            }
        }

        if (selectedSymptom.code == "OTHER") {
            OutlinedTextField(
                value = customDescription,
                onValueChange = { customDescription = it; onInputChanged() },
                placeholder = { Text("Mô tả triệu chứng bạn gặp phải") },
                modifier = Modifier.fillMaxWidth().padding(bottom = 22.dp),
                singleLine = true,
            )
        }

        if (selectedSymptom.code != "NONE") {
            Text("Mức độ", style = MaterialTheme.typography.titleMedium, modifier = Modifier.padding(bottom = 10.dp))
            Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Severity.entries.forEach { level ->
                    SeverityOption(level, picked = severity == level, modifier = Modifier.weight(1f)) {
                        severity = level
                        onInputChanged()
                    }
                }
            }
            if (severity == Severity.SEVERE) {
                Text(
                    "⚠ Mức \"Nặng\" sẽ cảnh báo ngay cho bác sĩ điều trị.",
                    style = MaterialTheme.typography.labelMedium,
                    color = extras.danger,
                    fontWeight = FontWeight.SemiBold,
                    modifier = Modifier.padding(top = 8.dp, bottom = 20.dp),
                )
            } else {
                Box(Modifier.padding(bottom = 20.dp))
            }
        } else {
            Box(Modifier.padding(bottom = 20.dp))
        }

        error?.let {
            Text(
                it,
                style = MaterialTheme.typography.bodyMedium,
                color = extras.danger,
                modifier = Modifier.padding(bottom = 12.dp),
            )
        }

        val otherMissing = selectedSymptom.code == "OTHER" && customDescription.isBlank()

        PrimaryButton(
            text = when {
                isSubmitting -> "Đang gửi…"
                isSubmitted -> "Đã gửi khảo sát"
                else -> "Gửi khảo sát"
            },
            onClick = {
                val submittedSeverity = if (selectedSymptom.code == "NONE") Severity.MILD else severity
                onSubmit(mood, selectedSymptom.code, submittedSeverity.name, customDescription.trim().takeIf { it.isNotEmpty() })
            },
            modifier = Modifier.fillMaxWidth(),
            enabled = !isSubmitting && !isSubmitted && !otherMissing,
        )
    }
}

@Composable
private fun MoodDot(value: Int, picked: Boolean, modifier: Modifier = Modifier, onClick: () -> Unit) {
    val extras = LocalDoselyColors.current
    Card(
        modifier = modifier.aspectRatio(1f),
        shape = RoundedCornerShape(12.dp),
        colors = CardDefaults.cardColors(containerColor = if (picked) MaterialTheme.colorScheme.primary else extras.surfaceAlt),
        onClick = onClick,
    ) {
        Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
            Text(
                "$value",
                style = MaterialTheme.typography.titleMedium,
                color = if (picked) Color.White else extras.inkMuted,
            )
        }
    }
}

@Composable
private fun SymptomChip(label: String, picked: Boolean, onClick: () -> Unit) {
    val extras = LocalDoselyColors.current
    Card(
        shape = RoundedCornerShape(999.dp),
        colors = CardDefaults.cardColors(containerColor = if (picked) extras.dangerTint else Color.Transparent),
        border = androidx.compose.foundation.BorderStroke(1.5.dp, if (picked) extras.danger else extras.border),
        onClick = onClick,
    ) {
        Text(
            label,
            style = MaterialTheme.typography.labelLarge,
            color = if (picked) extras.danger else extras.inkMuted,
            modifier = Modifier.padding(horizontal = 13.dp, vertical = 9.dp),
        )
    }
}

@Composable
private fun SeverityOption(level: Severity, picked: Boolean, modifier: Modifier = Modifier, onClick: () -> Unit) {
    val extras = LocalDoselyColors.current
    val selectedColor = if (level == Severity.SEVERE) extras.danger else MaterialTheme.colorScheme.primary
    Card(
        modifier = modifier,
        shape = RoundedCornerShape(10.dp),
        colors = CardDefaults.cardColors(containerColor = if (picked) selectedColor else Color.Transparent),
        border = androidx.compose.foundation.BorderStroke(1.5.dp, if (picked) selectedColor else extras.border),
        onClick = onClick,
    ) {
        Text(
            level.label,
            style = MaterialTheme.typography.labelLarge,
            color = if (picked) Color.White else extras.inkMuted,
            textAlign = TextAlign.Center,
            modifier = Modifier.fillMaxWidth().padding(vertical = 10.dp),
        )
    }
}

@com.dosely.app.ui.preview.DoselyScreenPreview
@Composable
private fun SurveyScreenPreview() = com.dosely.app.ui.preview.DoselyPreview {
    SurveyScreen(onSubmit = { _, _, _, _ -> })
}
