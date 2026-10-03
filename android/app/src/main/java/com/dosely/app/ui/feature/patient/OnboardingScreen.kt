package com.dosely.app.ui.feature.patient

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Bedtime
import androidx.compose.material.icons.filled.Restaurant
import androidx.compose.material.icons.filled.WbSunny
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import com.dosely.app.data.RoutineItem
import com.dosely.app.ui.components.PrimaryButton
import com.dosely.app.ui.theme.LocalDoselyColors

private val onboardingRoutineDefaults = listOf(
    RoutineItem("wake_time", "Thức dậy", "06:30"),
    RoutineItem("breakfast_time", "Ăn sáng", "07:00"),
    RoutineItem("lunch_time", "Ăn trưa", "11:30"),
    RoutineItem("dinner_time", "Ăn tối", "18:00"),
    RoutineItem("sleep_time", "Đi ngủ", "22:00"),
)

/**
 * Onboarding only captures routine times. Patient identity/profile data is
 * intentionally absent because it is created by the care team before login.
 */
@Composable
fun OnboardingScreen(
    routine: List<RoutineItem>,
    isSaving: Boolean,
    error: String?,
    onInputChanged: () -> Unit,
    onSaveRoutine: (List<RoutineItem>) -> Unit,
) {
    val extras = LocalDoselyColors.current
    var editedRoutine by remember(routine) { mutableStateOf(routine.withRequiredOnboardingItems()) }
    val canSave = !isSaving && editedRoutine.all { it.time.isValidRoutineTime() }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(horizontal = 24.dp, vertical = 20.dp),
    ) {
        Row(
            modifier = Modifier.fillMaxWidth().padding(bottom = 22.dp),
            horizontalArrangement = Arrangement.spacedBy(6.dp),
        ) {
            repeat(3) { index ->
                Box(
                    modifier = Modifier
                        .weight(1f)
                        .height(4.dp)
                        .background(
                            if (index < 2) MaterialTheme.colorScheme.primary else extras.border,
                            RoundedCornerShape(4.dp),
                        ),
                )
            }
        }

        Text("Thiết lập\nthói quen sinh hoạt", style = MaterialTheme.typography.headlineMedium)
        Text(
            "Chọn 5 mốc giờ để lịch nhắc thuốc phù hợp với sinh hoạt hằng ngày.",
            style = MaterialTheme.typography.bodyMedium,
            color = extras.inkMuted,
            modifier = Modifier.padding(top = 6.dp, bottom = 8.dp),
        )

        Column(modifier = Modifier.weight(1f)) {
            editedRoutine.forEachIndexed { index, item ->
                EditableRoutineRow(
                    item = item,
                    icon = onboardingIconFor(item.key),
                    onTimeChanged = { value ->
                        editedRoutine = editedRoutine.toMutableList().also { items ->
                            items[index] = item.copy(time = value)
                        }
                        onInputChanged()
                    },
                )
                if (index != editedRoutine.lastIndex) {
                    Box(Modifier.fillMaxWidth().height(1.dp).background(extras.border))
                }
            }
        }

        error?.let {
            Text(
                it,
                style = MaterialTheme.typography.bodyMedium,
                color = extras.danger,
                modifier = Modifier.padding(top = 8.dp),
            )
        }
        PrimaryButton(
            text = if (isSaving) "Đang lưu và tạo lịch…" else "Lưu & tạo lịch uống thuốc",
            onClick = { onSaveRoutine(editedRoutine) },
            modifier = Modifier.fillMaxWidth().padding(top = 16.dp),
            enabled = canSave,
        )
    }
}

private fun onboardingIconFor(key: String): ImageVector = when (key) {
    "wake_time" -> Icons.Filled.WbSunny
    "sleep_time" -> Icons.Filled.Bedtime
    else -> Icons.Filled.Restaurant
}

@Composable
private fun EditableRoutineRow(
    item: RoutineItem,
    icon: ImageVector,
    onTimeChanged: (String) -> Unit,
) {
    val extras = LocalDoselyColors.current
    Row(
        modifier = Modifier.fillMaxWidth().padding(vertical = 8.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(13.dp),
    ) {
        Card(
            shape = RoundedCornerShape(11.dp),
            colors = CardDefaults.cardColors(containerColor = extras.primaryTint),
            modifier = Modifier.size(40.dp),
        ) {
            Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                Icon(icon, contentDescription = null, tint = MaterialTheme.colorScheme.primary, modifier = Modifier.size(20.dp))
            }
        }
        Text(item.label, style = MaterialTheme.typography.titleMedium, modifier = Modifier.weight(1f))
        RoutineTimeField(
            time = item.time,
            onTimeChanged = onTimeChanged,
            modifier = Modifier.width(112.dp),
            shape = RoundedCornerShape(10.dp),
            textStyle = MaterialTheme.typography.titleMedium.copy(textAlign = TextAlign.Center),
        )
    }
}

private fun List<RoutineItem>.withRequiredOnboardingItems(): List<RoutineItem> {
    val byKey = associateBy(RoutineItem::key)
    return onboardingRoutineDefaults.map { default ->
        val existing = byKey[default.key]
        default.copy(time = existing?.time?.take(5)?.takeIf { it.isNotBlank() } ?: default.time)
    }
}

@com.dosely.app.ui.preview.DoselyScreenPreview
@Composable
private fun OnboardingScreenPreview() = com.dosely.app.ui.preview.DoselyPreview {
    OnboardingScreen(
        routine = com.dosely.app.ui.preview.previewRoutine,
        isSaving = false,
        error = null,
        onInputChanged = {},
        onSaveRoutine = {},
    )
}
