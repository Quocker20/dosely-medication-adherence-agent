package com.remindrx.app.ui.feature.patient

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
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
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ChevronRight
import androidx.compose.material.icons.filled.Lock
import androidx.compose.material.icons.filled.Schedule
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Switch
import androidx.compose.material3.SwitchDefaults
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import com.remindrx.app.data.MockRepository
import com.remindrx.app.data.RoutineItem
import com.remindrx.app.ui.components.PrimaryButton
import com.remindrx.app.ui.theme.LocalRemindRxColors

@Composable
fun SettingsScreen(
    routine: List<RoutineItem>,
    isSavingRoutine: Boolean,
    routineError: String?,
    onRoutineInputChanged: () -> Unit,
    onSaveRoutine: (List<RoutineItem>) -> Unit,
    onChangePin: () -> Unit,
) {
    val extras = LocalRemindRxColors.current
    var editedRoutine by remember(routine) { mutableStateOf(routine) }
    val canSaveRoutine = editedRoutine != routine &&
        editedRoutine.isNotEmpty() &&
        editedRoutine.all { it.time.isValidTime() } &&
        !isSavingRoutine

    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(horizontal = 20.dp),
    ) {
        Row(
            modifier = Modifier.fillMaxWidth().padding(vertical = 18.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Box(
                modifier = Modifier.size(46.dp).background(MaterialTheme.colorScheme.primary, CircleShape),
                contentAlignment = Alignment.Center,
            ) {
                Text("TL", color = Color.White, style = MaterialTheme.typography.titleMedium)
            }
            Column(Modifier.weight(1f)) {
                Text(MockRepository.PATIENT_NAME, style = MaterialTheme.typography.titleMedium)
                Text(
                    MockRepository.PATIENT_PHONE,
                    style = MaterialTheme.typography.labelMedium,
                    color = extras.inkMuted,
                    fontWeight = FontWeight.Normal,
                )
            }
            Text("Sửa", style = MaterialTheme.typography.labelLarge, color = MaterialTheme.colorScheme.primary)
        }
        Divider()

        SettingsSection("Bảo mật") {
            SettingsActionRow(
                title = "Đổi mã PIN",
                subtitle = "Tạo mã PIN 6 chữ số mới",
                onClick = onChangePin,
            )
        }
        Divider()

        SettingsSection("Thói quen sinh hoạt") {
            Row(
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(8.dp),
                modifier = Modifier.padding(bottom = 8.dp),
            ) {
                Icon(
                    Icons.Filled.Schedule,
                    contentDescription = null,
                    tint = MaterialTheme.colorScheme.primary,
                    modifier = Modifier.size(20.dp),
                )
                Text(
                    "Sửa các mốc giờ để lịch nhắc thuốc phù hợp với sinh hoạt của bạn.",
                    style = MaterialTheme.typography.labelMedium,
                    color = extras.inkMuted,
                    fontWeight = FontWeight.Normal,
                    modifier = Modifier.weight(1f),
                )
            }

            editedRoutine.forEachIndexed { index, item ->
                Row(
                    modifier = Modifier.fillMaxWidth().padding(vertical = 5.dp),
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(12.dp),
                ) {
                    Text(item.label, style = MaterialTheme.typography.bodyMedium, modifier = Modifier.weight(1f))
                    OutlinedTextField(
                        value = item.time,
                        onValueChange = { value ->
                            editedRoutine = editedRoutine.toMutableList().also { items ->
                                items[index] = item.copy(time = formatTimeInput(value))
                            }
                            onRoutineInputChanged()
                        },
                        modifier = Modifier.width(112.dp),
                        shape = RoundedCornerShape(12.dp),
                        textStyle = MaterialTheme.typography.bodyLarge.copy(textAlign = TextAlign.Center),
                        placeholder = { Text("HH:mm") },
                        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                        isError = item.time.length == 5 && !item.time.isValidTime(),
                        singleLine = true,
                    )
                }
            }

            if (routineError != null) {
                Text(
                    routineError,
                    style = MaterialTheme.typography.bodyMedium,
                    color = extras.danger,
                    modifier = Modifier.padding(top = 8.dp),
                )
            }

            PrimaryButton(
                text = if (isSavingRoutine) "Đang lưu…" else "Lưu thói quen sinh hoạt",
                onClick = { onSaveRoutine(editedRoutine) },
                modifier = Modifier.fillMaxWidth().padding(top = 12.dp),
                enabled = canSaveRoutine,
            )
        }
        Divider()

        SettingsSection("Người liên hệ khẩn cấp") {
            Row(
                Modifier.fillMaxWidth().padding(vertical = 7.dp),
                horizontalArrangement = Arrangement.SpaceBetween,
            ) {
                Text(
                    "${MockRepository.emergencyContact.name} (${MockRepository.emergencyContact.relation})",
                    style = MaterialTheme.typography.bodyMedium,
                )
                Text(
                    MockRepository.emergencyContact.phone,
                    style = MaterialTheme.typography.labelMedium,
                    color = extras.inkMuted,
                    fontWeight = FontWeight.Normal,
                )
            }
            Text(
                "+ Thêm người liên hệ",
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.primary,
                modifier = Modifier.padding(vertical = 7.dp),
            )
        }
        Divider()

        SettingsSection("Kênh nhắc nhở") {
            ToggleRow("Web Push", initiallyOn = true)
            ToggleRow("Zalo", initiallyOn = true)
            ToggleRow("Gọi điện khi khẩn cấp", initiallyOn = true)
        }
        Divider()

        SettingsSection("Hiển thị") {
            ToggleRow("Cỡ chữ lớn", initiallyOn = true)
            ToggleRow("Độ tương phản cao", initiallyOn = false)
        }
        Divider()

        Row(
            modifier = Modifier.fillMaxWidth().padding(vertical = 14.dp),
            horizontalArrangement = Arrangement.SpaceBetween,
        ) {
            Text("Ngôn ngữ", style = MaterialTheme.typography.bodyMedium)
            Text(
                "Tiếng Việt",
                style = MaterialTheme.typography.labelMedium,
                color = extras.inkMuted,
                fontWeight = FontWeight.Normal,
            )
        }
        Text(
            "Đăng xuất",
            style = MaterialTheme.typography.bodyMedium,
            color = extras.danger,
            fontWeight = FontWeight.Bold,
            modifier = Modifier.padding(bottom = 24.dp),
        )
    }
}

@Composable
private fun SettingsActionRow(title: String, subtitle: String, onClick: () -> Unit) {
    val extras = LocalRemindRxColors.current
    Row(
        modifier = Modifier.fillMaxWidth().clickable(onClick = onClick).padding(vertical = 8.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Icon(Icons.Filled.Lock, contentDescription = null, tint = MaterialTheme.colorScheme.primary)
        Column(Modifier.weight(1f)) {
            Text(title, style = MaterialTheme.typography.bodyMedium)
            Text(
                subtitle,
                style = MaterialTheme.typography.labelMedium,
                color = extras.inkMuted,
                fontWeight = FontWeight.Normal,
            )
        }
        Icon(Icons.Filled.ChevronRight, contentDescription = null, tint = extras.inkMuted)
    }
}

@Composable
private fun SettingsSection(title: String, content: @Composable () -> Unit) {
    val extras = LocalRemindRxColors.current
    Column(Modifier.padding(vertical = 16.dp)) {
        Text(
            title.uppercase(),
            style = MaterialTheme.typography.labelSmall,
            color = extras.inkMuted,
            modifier = Modifier.padding(bottom = 10.dp),
        )
        content()
    }
}

@Composable
private fun ToggleRow(label: String, initiallyOn: Boolean) {
    var on by remember { mutableStateOf(initiallyOn) }
    Row(
        modifier = Modifier.fillMaxWidth().padding(vertical = 6.dp),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(label, style = MaterialTheme.typography.bodyMedium)
        Switch(
            checked = on,
            onCheckedChange = { on = it },
            colors = SwitchDefaults.colors(checkedTrackColor = MaterialTheme.colorScheme.primary),
        )
    }
}

@Composable
private fun Divider() {
    val extras = LocalRemindRxColors.current
    Box(Modifier.fillMaxWidth().height(1.dp).background(extras.border))
}

private fun formatTimeInput(value: String): String {
    val digits = value.filter(Char::isDigit).take(4)
    return if (digits.length <= 2) digits else "${digits.take(2)}:${digits.drop(2)}"
}

private fun String.isValidTime(): Boolean {
    if (!matches(Regex("\\d{2}:\\d{2}"))) return false
    val (hour, minute) = split(':').map(String::toInt)
    return hour in 0..23 && minute in 0..59
}
