package com.remindrx.app.ui.components

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Checklist
import androidx.compose.material.icons.filled.Home
import androidx.compose.material.icons.filled.Lock
import androidx.compose.material.icons.filled.Medication
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material.icons.outlined.Notifications
import androidx.compose.material.icons.outlined.Restaurant
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.FloatingActionButton
import androidx.compose.material3.FloatingActionButtonDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.NavigationBarItemDefaults
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.Button
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.remindrx.app.data.DoseStatus
import com.remindrx.app.data.DoseToday
import com.remindrx.app.data.MealRelation
import com.remindrx.app.ui.theme.LocalRemindRxColors

enum class ChipTone { SUCCESS, WARNING, DANGER, NEUTRAL, MUTED }

@Composable
fun StatusChip(text: String, tone: ChipTone, modifier: Modifier = Modifier) {
    val extras = LocalRemindRxColors.current
    val (fg, bg) = when (tone) {
        ChipTone.SUCCESS -> extras.success to extras.successTint
        ChipTone.WARNING -> extras.warning to extras.warningTint
        ChipTone.DANGER -> extras.danger to extras.dangerTint
        ChipTone.NEUTRAL -> MaterialTheme.colorScheme.primary to extras.primaryTint
        ChipTone.MUTED -> extras.inkMuted to extras.surfaceAlt
    }
    Card(
        modifier = modifier,
        shape = RoundedCornerShape(999.dp),
        colors = CardDefaults.cardColors(containerColor = bg),
    ) {
        Text(
            text = text,
            color = fg,
            style = MaterialTheme.typography.labelMedium,
            modifier = Modifier.padding(horizontal = 10.dp, vertical = 5.dp),
        )
    }
}

@Composable
fun TimeChip(time: String, modifier: Modifier = Modifier) {
    val extras = LocalRemindRxColors.current
    Card(
        modifier = modifier,
        shape = RoundedCornerShape(8.dp),
        colors = CardDefaults.cardColors(containerColor = extras.primaryTint),
    ) {
        Text(
            text = time,
            color = MaterialTheme.colorScheme.primary,
            style = MaterialTheme.typography.labelMedium,
            modifier = Modifier.padding(horizontal = 9.dp, vertical = 5.dp),
        )
    }
}

@Composable
fun PrimaryButton(
    text: String,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    enabled: Boolean = true,
) {
    Button(
        onClick = onClick,
        enabled = enabled,
        modifier = modifier,
        shape = RoundedCornerShape(14.dp),
        colors = ButtonDefaults.buttonColors(containerColor = MaterialTheme.colorScheme.primary),
    ) {
        Text(text, style = MaterialTheme.typography.labelLarge, modifier = Modifier.padding(vertical = 6.dp))
    }
}

@Composable
fun SuccessButton(text: String, onClick: () -> Unit, modifier: Modifier = Modifier) {
    val extras = LocalRemindRxColors.current
    Button(
        onClick = onClick,
        modifier = modifier,
        shape = RoundedCornerShape(14.dp),
        colors = ButtonDefaults.buttonColors(containerColor = extras.success),
    ) {
        Text(text, style = MaterialTheme.typography.labelLarge, modifier = Modifier.padding(vertical = 6.dp))
    }
}

@Composable
fun WarningOutlineButton(text: String, onClick: () -> Unit, modifier: Modifier = Modifier) {
    val extras = LocalRemindRxColors.current
    OutlinedButton(
        onClick = onClick,
        modifier = modifier,
        shape = RoundedCornerShape(14.dp),
        colors = ButtonDefaults.outlinedButtonColors(containerColor = extras.warningTint, contentColor = extras.warning),
        border = androidx.compose.foundation.BorderStroke(1.5.dp, extras.warning),
    ) {
        Text(text, style = MaterialTheme.typography.labelLarge, modifier = Modifier.padding(vertical = 6.dp))
    }
}

@Composable
fun GhostButton(text: String, onClick: () -> Unit, modifier: Modifier = Modifier) {
    val extras = LocalRemindRxColors.current
    TextButton(onClick = onClick, modifier = modifier) {
        Text(text, style = MaterialTheme.typography.labelLarge, color = extras.inkMuted)
    }
}

@Composable
fun GuardrailNote(text: String, modifier: Modifier = Modifier) {
    val extras = LocalRemindRxColors.current
    Card(
        modifier = modifier,
        shape = RoundedCornerShape(12.dp),
        colors = CardDefaults.cardColors(containerColor = extras.surfaceAlt),
    ) {
        Row(
            modifier = Modifier.padding(12.dp),
            horizontalArrangement = Arrangement.spacedBy(9.dp),
        ) {
            Icon(
                Icons.Filled.Warning,
                contentDescription = null,
                tint = extras.inkMuted,
                modifier = Modifier.size(16.dp),
            )
            Text(text, style = MaterialTheme.typography.labelMedium, color = extras.inkMuted, fontWeight = FontWeight.Normal)
        }
    }
}

@Composable
fun AlertBellButton(unreadCount: Int, onClick: () -> Unit, modifier: Modifier = Modifier) {
    val extras = LocalRemindRxColors.current
    Box(modifier = modifier) {
        IconButton(onClick = onClick) {
            Icon(Icons.Outlined.Notifications, contentDescription = "Thông báo", tint = extras.inkMuted)
        }
        if (unreadCount > 0) {
            Box(
                modifier = Modifier
                    .align(Alignment.TopEnd)
                    .padding(top = 8.dp, end = 8.dp)
                    .size(9.dp)
                    .background(extras.danger, CircleShape),
            )
        }
    }
}

private fun mealRelationLabel(relation: MealRelation): String = when (relation) {
    MealRelation.NONE -> ""
    MealRelation.BEFORE_MEAL -> "Trước ăn"
    MealRelation.AFTER_MEAL -> "Sau ăn"
    MealRelation.WITH_MEAL -> "Cùng bữa"
}

/**
 * Dose card for the daily schedule list. Only DoseStatus.UPCOMING renders the
 * inline action row — resolved/locked doses are read-only, matching adherence
 * being append-only once logged (see AdherenceLogDetailResponse).
 */
@Composable
fun TodayDoseCard(
    dose: DoseToday,
    onTaken: () -> Unit,
    onLate: () -> Unit,
    onSkip: () -> Unit,
    onOpen: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val extras = LocalRemindRxColors.current
    val isLocked = dose.status == DoseStatus.LOCKED

    Card(
        onClick = onOpen,
        modifier = modifier.fillMaxWidth().alpha(if (isLocked) 0.55f else 1f),
        shape = RoundedCornerShape(16.dp),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
        elevation = CardDefaults.cardElevation(defaultElevation = 1.dp),
    ) {
        Column(Modifier.padding(14.dp)) {
            Row(verticalAlignment = Alignment.Top, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                Text(
                    dose.time,
                    style = MaterialTheme.typography.titleMedium,
                    color = extras.inkMuted,
                    modifier = Modifier.width(52.dp),
                )
                Column(Modifier.weight(1f)) {
                    Text(dose.medicationName, style = MaterialTheme.typography.titleMedium)
                    Row(
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.spacedBy(4.dp),
                        modifier = Modifier.padding(top = 2.dp),
                    ) {
                        Text(dose.doseLabel, style = MaterialTheme.typography.labelMedium, color = extras.inkMuted, fontWeight = FontWeight.Normal)
                        if (dose.mealRelation != MealRelation.NONE) {
                            Icon(Icons.Outlined.Restaurant, contentDescription = null, tint = extras.inkMuted, modifier = Modifier.size(13.dp))
                            Text(mealRelationLabel(dose.mealRelation), style = MaterialTheme.typography.labelMedium, color = extras.inkMuted, fontWeight = FontWeight.Normal)
                        }
                    }
                }
                if (isLocked) {
                    Icon(Icons.Filled.Lock, contentDescription = null, tint = extras.inkMuted, modifier = Modifier.size(14.dp))
                }
                when (dose.status) {
                    DoseStatus.TAKEN -> StatusChip("Đã uống", ChipTone.SUCCESS)
                    DoseStatus.LATE -> StatusChip("Uống muộn", ChipTone.WARNING)
                    DoseStatus.SNOOZED -> StatusChip("Đã hoãn ${dose.snoozeMinutes ?: 15} phút", ChipTone.WARNING)
                    DoseStatus.SKIPPED -> StatusChip("Bỏ qua", ChipTone.MUTED)
                    DoseStatus.LOCKED -> StatusChip("Chưa đến giờ", ChipTone.MUTED)
                    DoseStatus.UPCOMING -> {}
                }
            }

            if (dose.status == DoseStatus.UPCOMING) {
                Row(
                    modifier = Modifier.fillMaxWidth().padding(top = 12.dp),
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    SuccessButton("Đã uống", onClick = onTaken, modifier = Modifier.weight(1f))
                    WarningOutlineButton("Uống muộn", onClick = onLate, modifier = Modifier.weight(1f))
                }
                GhostButton("Bỏ qua cữ này", onClick = onSkip, modifier = Modifier.fillMaxWidth())
            }
        }
    }
}

private data class BottomDestination(val route: String, val label: String)

private val bottomDestinations = listOf(
    BottomDestination("dashboard", "Lịch uống thuốc"),
    BottomDestination("prescription", "Đơn thuốc"),
    BottomDestination("survey", "Khảo sát"),
    BottomDestination("settings", "Cài đặt"),
)

@Composable
fun RemindRxBottomBar(currentRoute: String?, onNavigate: (String) -> Unit) {
    NavigationBar {
        bottomDestinations.forEach { dest ->
            NavigationBarItem(
                selected = currentRoute == dest.route,
                onClick = { onNavigate(dest.route) },
                icon = {
                    Icon(
                        when (dest.route) {
                            "dashboard" -> Icons.Filled.Home
                            "prescription" -> Icons.Filled.Medication
                            "survey" -> Icons.Filled.Checklist
                            else -> Icons.Filled.Settings
                        },
                        contentDescription = dest.label,
                    )
                },
                label = { Text(dest.label, style = MaterialTheme.typography.labelSmall) },
                colors = NavigationBarItemDefaults.colors(
                    selectedIconColor = MaterialTheme.colorScheme.primary,
                    selectedTextColor = MaterialTheme.colorScheme.primary,
                    indicatorColor = LocalRemindRxColors.current.primaryTint,
                    unselectedIconColor = LocalRemindRxColors.current.inkMuted,
                    unselectedTextColor = LocalRemindRxColors.current.inkMuted,
                ),
            )
        }
    }
}

@Composable
fun SosFab(onClick: () -> Unit) {
    val extras = LocalRemindRxColors.current
    FloatingActionButton(
        onClick = onClick,
        shape = CircleShape,
        containerColor = extras.danger,
        contentColor = Color.White,
        elevation = FloatingActionButtonDefaults.elevation(defaultElevation = 6.dp),
    ) {
        Icon(Icons.Filled.Warning, contentDescription = "SOS khẩn cấp")
    }
}
