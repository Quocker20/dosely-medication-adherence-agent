package com.remindrx.app.ui.screens

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
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.MaterialTheme
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
import androidx.compose.ui.unit.dp
import com.remindrx.app.data.MockRepository
import com.remindrx.app.ui.theme.LocalRemindRxColors

@Composable
fun SettingsScreen() {
    val extras = LocalRemindRxColors.current

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
                Text(MockRepository.PATIENT_PHONE, style = MaterialTheme.typography.labelMedium, color = extras.inkMuted, fontWeight = FontWeight.Normal)
            }
            Text("Sửa", style = MaterialTheme.typography.labelLarge, color = MaterialTheme.colorScheme.primary)
        }
        Divider()

        SettingsSection("Người liên hệ khẩn cấp") {
            Row(Modifier.fillMaxWidth().padding(vertical = 7.dp), horizontalArrangement = Arrangement.SpaceBetween) {
                Text("${MockRepository.emergencyContact.name} (${MockRepository.emergencyContact.relation})", style = MaterialTheme.typography.bodyMedium)
                Text(MockRepository.emergencyContact.phone, style = MaterialTheme.typography.labelMedium, color = extras.inkMuted, fontWeight = FontWeight.Normal)
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
            Text("Tiếng Việt", style = MaterialTheme.typography.labelMedium, color = extras.inkMuted, fontWeight = FontWeight.Normal)
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
