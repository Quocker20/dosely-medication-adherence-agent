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
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.Logout
import androidx.compose.material.icons.filled.ChevronRight
import androidx.compose.material.icons.filled.History
import androidx.compose.material.icons.filled.Lock
import androidx.compose.material.icons.filled.People
import androidx.compose.material.icons.filled.Schedule
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import com.remindrx.app.data.RoutineItem
import com.remindrx.app.ui.components.PrimaryButton
import com.remindrx.app.ui.theme.LocalRemindRxColors

private val settingsRoutineDefaults = listOf(
    RoutineItem("wake_time", "Thức dậy", "06:30"),
    RoutineItem("breakfast_time", "Ăn sáng", "07:00"),
    RoutineItem("lunch_time", "Ăn trưa", "11:30"),
    RoutineItem("dinner_time", "Ăn tối", "18:00"),
    RoutineItem("sleep_time", "Đi ngủ", "22:00"),
)

@Composable
fun SettingsScreen(
    routine: List<RoutineItem>,
    isSavingRoutine: Boolean,
    routineError: String?,
    onRoutineInputChanged: () -> Unit,
    onSaveRoutine: (List<RoutineItem>) -> Unit,
    onChangePin: () -> Unit,
    onOpenCaregivers: () -> Unit = {},
    onOpenAdherenceHistory: () -> Unit = {},
    isLoggingOut: Boolean = false,
    onLogout: () -> Unit = {},
) {
    val extras = LocalRemindRxColors.current
    val normalizedRoutine = remember(routine) { routine.withRequiredSettingsItems() }
    var editedRoutine by remember(normalizedRoutine) { mutableStateOf(normalizedRoutine) }
    val canSaveRoutine = editedRoutine != normalizedRoutine &&
        editedRoutine.all { it.time.isValidSettingsTime() } &&
        !isSavingRoutine

    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(horizontal = 20.dp),
    ) {
        Text(
            "Cài đặt",
            style = MaterialTheme.typography.headlineMedium,
            modifier = Modifier.padding(top = 22.dp, bottom = 16.dp),
        )
        SettingsDivider()

        SettingsSection("Tài khoản") {
            SettingsActionRow(
                icon = Icons.Filled.Lock,
                title = "Đổi mã PIN",
                subtitle = "Tạo mã PIN 6 chữ số mới",
                onClick = onChangePin,
            )
        }
        SettingsDivider()

        SettingsSection("Theo dõi dùng thuốc") {
            SettingsActionRow(
                icon = Icons.Filled.History,
                title = "Lịch sử dùng thuốc",
                subtitle = "Xem kết quả tuân thủ và các lần đã ghi nhận",
                onClick = onOpenAdherenceHistory,
            )
        }
        SettingsDivider()

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
                    "Sửa các mốc giờ để tạo lại lịch nhắc thuốc phù hợp với sinh hoạt của bạn.",
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
                                items[index] = item.copy(time = formatSettingsTimeInput(value))
                            }
                            onRoutineInputChanged()
                        },
                        modifier = Modifier.width(112.dp),
                        shape = RoundedCornerShape(12.dp),
                        textStyle = MaterialTheme.typography.bodyLarge.copy(textAlign = TextAlign.Center),
                        placeholder = { Text("HH:mm") },
                        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                        isError = item.time.length == 5 && !item.time.isValidSettingsTime(),
                        singleLine = true,
                    )
                }
            }

            routineError?.let {
                Text(
                    it,
                    style = MaterialTheme.typography.bodyMedium,
                    color = extras.danger,
                    modifier = Modifier.padding(top = 8.dp),
                )
            }

            PrimaryButton(
                text = if (isSavingRoutine) "Đang lưu và tạo lại lịch…" else "Lưu thói quen sinh hoạt",
                onClick = { onSaveRoutine(editedRoutine) },
                modifier = Modifier.fillMaxWidth().padding(top = 12.dp),
                enabled = canSaveRoutine,
            )
        }
        SettingsDivider()

        SettingsSection("Người chăm sóc") {
            SettingsActionRow(
                icon = Icons.Filled.People,
                title = "Quản lý người chăm sóc",
                subtitle = "Thêm hoặc gỡ tài khoản được liên kết",
                onClick = onOpenCaregivers,
            )
        }
        SettingsDivider()

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
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .clickable(enabled = !isLoggingOut, onClick = onLogout)
                .padding(vertical = 16.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            Icon(Icons.AutoMirrored.Filled.Logout, contentDescription = null, tint = extras.danger)
            Text(
                if (isLoggingOut) "Đang đăng xuất…" else "Đăng xuất",
                style = MaterialTheme.typography.bodyMedium,
                color = extras.danger,
                fontWeight = FontWeight.Bold,
            )
        }
    }
}

@Composable
private fun SettingsActionRow(
    icon: ImageVector,
    title: String,
    subtitle: String,
    onClick: () -> Unit,
) {
    val extras = LocalRemindRxColors.current
    Row(
        modifier = Modifier.fillMaxWidth().clickable(onClick = onClick).padding(vertical = 8.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Icon(icon, contentDescription = null, tint = MaterialTheme.colorScheme.primary)
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
private fun SettingsDivider() {
    val extras = LocalRemindRxColors.current
    Box(Modifier.fillMaxWidth().height(1.dp).background(extras.border))
}

private fun List<RoutineItem>.withRequiredSettingsItems(): List<RoutineItem> {
    val byKey = associateBy(RoutineItem::key)
    return settingsRoutineDefaults.map { default ->
        val existing = byKey[default.key]
        default.copy(time = existing?.time?.take(5)?.takeIf { it.isNotBlank() } ?: default.time)
    }
}

private fun formatSettingsTimeInput(value: String): String {
    val digits = value.filter(Char::isDigit).take(4)
    return if (digits.length <= 2) digits else "${digits.take(2)}:${digits.drop(2)}"
}

private fun String.isValidSettingsTime(): Boolean {
    if (!matches(Regex("\\d{2}:\\d{2}"))) return false
    val (hour, minute) = split(':').map(String::toInt)
    return hour in 0..23 && minute in 0..59
}

@com.remindrx.app.ui.preview.RemindRxScreenPreview
@Composable
private fun SettingsScreenPreview() = com.remindrx.app.ui.preview.RemindRxPreview {
    SettingsScreen(
        routine = com.remindrx.app.ui.preview.previewRoutine,
        isSavingRoutine = false,
        routineError = null,
        onRoutineInputChanged = {},
        onSaveRoutine = {},
        onChangePin = {},
        onOpenCaregivers = {},
        onOpenAdherenceHistory = {},
        onLogout = {},
    )
}
