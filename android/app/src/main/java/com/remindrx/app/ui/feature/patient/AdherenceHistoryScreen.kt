package com.remindrx.app.ui.feature.patient

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.ChevronLeft
import androidx.compose.material.icons.filled.ChevronRight
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.remindrx.app.ui.components.ChipTone
import com.remindrx.app.ui.components.PrimaryButton
import com.remindrx.app.ui.components.StatusChip
import com.remindrx.app.ui.theme.LocalRemindRxColors
import kotlin.math.roundToInt

data class AdherenceSummaryUi(
    val fromDateLabel: String,
    val toDateLabel: String,
    val adherenceRate: Float,
    val totalDoses: Int,
    val takenDoses: Int,
    val skippedDoses: Int,
    val missedDoses: Int,
)

data class AdherenceLogUi(
    val id: String,
    val action: String,
    val performedAtLabel: String,
    val takenLate: Boolean = false,
    val note: String? = null,
)

@Composable
fun AdherenceHistoryScreen(
    summary: AdherenceSummaryUi?,
    logs: List<AdherenceLogUi>,
    isLoading: Boolean,
    error: String?,
    hasMore: Boolean,
    isLoadingMore: Boolean,
    canGoNextWeek: Boolean,
    onBack: () -> Unit,
    onRetry: () -> Unit,
    onPreviousWeek: () -> Unit,
    onNextWeek: () -> Unit,
    onLoadMore: () -> Unit,
) {
    val extras = LocalRemindRxColors.current
    LazyColumn(
        modifier = Modifier.fillMaxSize().padding(horizontal = 20.dp),
        contentPadding = PaddingValues(bottom = 28.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        item {
            Row(
                modifier = Modifier.fillMaxWidth().padding(top = 10.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                IconButton(onClick = onBack) {
                    Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Quay lại")
                }
                Text("Lịch sử dùng thuốc", style = MaterialTheme.typography.headlineMedium)
            }
        }

        item {
            Row(
                modifier = Modifier.fillMaxWidth(),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.SpaceBetween,
            ) {
                IconButton(onClick = onPreviousWeek) {
                    Icon(Icons.Filled.ChevronLeft, contentDescription = "Tuần trước")
                }
                Text(
                    summary?.let { "${it.fromDateLabel} – ${it.toDateLabel}" } ?: "Tuần hiện tại",
                    style = MaterialTheme.typography.titleMedium,
                )
                IconButton(onClick = onNextWeek, enabled = canGoNextWeek) {
                    Icon(Icons.Filled.ChevronRight, contentDescription = "Tuần sau")
                }
            }
        }

        if (isLoading) {
            item {
                Row(Modifier.fillMaxWidth().padding(36.dp), horizontalArrangement = Arrangement.Center) {
                    CircularProgressIndicator()
                }
            }
        } else if (error != null) {
            item {
                Column(Modifier.fillMaxWidth(), horizontalAlignment = Alignment.CenterHorizontally) {
                    Text(error, style = MaterialTheme.typography.bodyMedium, color = extras.danger)
                    PrimaryButton("Thử lại", onClick = onRetry, modifier = Modifier.padding(top = 12.dp))
                }
            }
        } else {
            summary?.let { adherence ->
                item { AdherenceSummaryCard(adherence) }
            }

            item {
                Text("Các lần ghi nhận", style = MaterialTheme.typography.titleMedium, modifier = Modifier.padding(top = 4.dp))
            }

            if (logs.isEmpty()) {
                item {
                    Text(
                        "Chưa có lần dùng thuốc nào được ghi nhận trong tuần này.",
                        style = MaterialTheme.typography.bodyMedium,
                        color = extras.inkMuted,
                        modifier = Modifier.padding(vertical = 18.dp),
                    )
                }
            } else {
                items(logs, key = AdherenceLogUi::id) { log -> AdherenceLogRow(log) }
            }

            if (hasMore || isLoadingMore) {
                item {
                    TextButton(
                        onClick = onLoadMore,
                        enabled = !isLoadingMore,
                        modifier = Modifier.fillMaxWidth(),
                    ) {
                        if (isLoadingMore) {
                            CircularProgressIndicator(modifier = Modifier.padding(4.dp))
                        } else {
                            Text("Xem thêm")
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun AdherenceSummaryCard(summary: AdherenceSummaryUi) {
    val extras = LocalRemindRxColors.current
    Card(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(18.dp),
        colors = CardDefaults.cardColors(containerColor = extras.primaryTint),
    ) {
        Column(Modifier.padding(16.dp)) {
            Text("Tỷ lệ tuân thủ", style = MaterialTheme.typography.labelMedium, color = extras.inkMuted)
            Text(
                "${summary.adherenceRate.coerceIn(0f, 100f).roundToInt()}%",
                style = MaterialTheme.typography.headlineMedium,
                color = MaterialTheme.colorScheme.primary,
                modifier = Modifier.padding(top = 3.dp, bottom = 12.dp),
            )
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                SummaryMetric("Tổng cữ", summary.totalDoses)
                SummaryMetric("Đã uống", summary.takenDoses)
                SummaryMetric("Bỏ qua", summary.skippedDoses)
                SummaryMetric("Bỏ lỡ", summary.missedDoses)
            }
        }
    }
}

@Composable
private fun SummaryMetric(label: String, value: Int) {
    val extras = LocalRemindRxColors.current
    Column(horizontalAlignment = Alignment.CenterHorizontally) {
        Text(value.toString(), style = MaterialTheme.typography.titleMedium)
        Text(label, style = MaterialTheme.typography.labelSmall, color = extras.inkMuted)
    }
}

@Composable
private fun AdherenceLogRow(log: AdherenceLogUi) {
    val extras = LocalRemindRxColors.current
    val (label, tone) = when {
        log.takenLate -> "Uống muộn" to ChipTone.WARNING
        log.action == "TAKEN" -> "Đã uống" to ChipTone.SUCCESS
        log.action == "SKIPPED" -> "Bỏ qua" to ChipTone.MUTED
        log.action == "SNOOZE" -> "Đã hoãn" to ChipTone.WARNING
        else -> log.action to ChipTone.NEUTRAL
    }
    Card(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(14.dp),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
        border = BorderStroke(1.dp, extras.border),
    ) {
        Row(
            modifier = Modifier.fillMaxWidth().padding(14.dp),
            verticalAlignment = Alignment.Top,
            horizontalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            Column(Modifier.weight(1f)) {
                Text(log.performedAtLabel, style = MaterialTheme.typography.bodyMedium, fontWeight = FontWeight.SemiBold)
                log.note?.takeIf(String::isNotBlank)?.let { note ->
                    Text(
                        note,
                        style = MaterialTheme.typography.labelMedium,
                        color = extras.inkMuted,
                        fontWeight = FontWeight.Normal,
                        modifier = Modifier.padding(top = 4.dp),
                    )
                }
            }
            StatusChip(label, tone)
        }
    }
}

@com.remindrx.app.ui.preview.RemindRxScreenPreview
@Composable
private fun AdherenceHistoryScreenPreview() = com.remindrx.app.ui.preview.RemindRxPreview {
    AdherenceHistoryScreen(
        summary = com.remindrx.app.ui.preview.previewAdherenceSummary,
        logs = com.remindrx.app.ui.preview.previewAdherenceLogs,
        isLoading = false,
        error = null,
        hasMore = true,
        isLoadingMore = false,
        canGoNextWeek = false,
        onBack = {},
        onRetry = {},
        onPreviousWeek = {},
        onNextWeek = {},
        onLoadMore = {},
    )
}
