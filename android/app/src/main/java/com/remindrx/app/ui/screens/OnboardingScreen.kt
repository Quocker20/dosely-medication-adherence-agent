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
import androidx.compose.foundation.shape.CircleShape
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
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import com.remindrx.app.data.RoutineItem
import com.remindrx.app.ui.components.PrimaryButton
import com.remindrx.app.ui.theme.LocalRemindRxColors

@Composable
fun OnboardingScreen(
    routine: List<RoutineItem>,
    isLoading: Boolean,
    error: String?,
    onRetry: () -> Unit,
    onDone: () -> Unit,
) {
    val extras = LocalRemindRxColors.current

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
                        .background(if (index < 2) MaterialTheme.colorScheme.primary else extras.border, RoundedCornerShape(4.dp)),
                )
            }
        }

        Text(
            "Cho chúng tôi biết\nthói quen của bạn",
            style = MaterialTheme.typography.headlineMedium,
        )
        Text(
            "Giúp lịch nhắc thuốc phù hợp với sinh hoạt hằng ngày.",
            style = MaterialTheme.typography.bodyMedium,
            color = extras.inkMuted,
            modifier = Modifier.padding(top = 6.dp, bottom = 8.dp),
        )

        Column(modifier = Modifier.weight(1f)) {
            routine.forEachIndexed { index, item ->
                RoutineRow(item, icon = iconFor(item.label))
                if (index != routine.lastIndex) {
                    Box(Modifier.fillMaxWidth().height(1.dp).background(extras.border))
                }
            }
        }

        if (isLoading) {
            Text("Đang tải lịch sinh hoạt…", style = MaterialTheme.typography.bodyMedium, color = extras.inkMuted)
        }
        if (error != null) {
            Text(error, style = MaterialTheme.typography.bodyMedium, color = extras.danger)
            PrimaryButton("Thử lại", onClick = onRetry, modifier = Modifier.fillMaxWidth().padding(top = 8.dp))
        }
        PrimaryButton("Lưu & tạo lịch uống thuốc", onClick = onDone, modifier = Modifier.fillMaxWidth().padding(top = 16.dp))
    }
}

private fun iconFor(label: String): ImageVector = when (label) {
    "Thức dậy" -> Icons.Filled.WbSunny
    "Đi ngủ" -> Icons.Filled.Bedtime
    else -> Icons.Filled.Restaurant
}

@Composable
private fun RoutineRow(item: RoutineItem, icon: ImageVector) {
    val extras = LocalRemindRxColors.current
    Row(
        modifier = Modifier.fillMaxWidth().padding(vertical = 13.dp),
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
        Card(
            shape = RoundedCornerShape(10.dp),
            colors = CardDefaults.cardColors(containerColor = extras.surfaceAlt),
        ) {
            Text(
                item.time,
                style = MaterialTheme.typography.titleMedium,
                textAlign = TextAlign.Center,
                modifier = Modifier.padding(horizontal = 12.dp, vertical = 7.dp),
            )
        }
    }
}
