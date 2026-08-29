package com.remindrx.app.ui.components

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CloudOff
import androidx.compose.material.icons.filled.Sync
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.remindrx.app.ui.theme.LocalRemindRxColors

@Composable
fun OfflineBanner(
    isOnline: Boolean,
    pendingSyncCount: Int,
    modifier: Modifier = Modifier,
) {
    if (isOnline && pendingSyncCount == 0) return

    val extras = LocalRemindRxColors.current
    val text = when {
        !isOnline && pendingSyncCount > 0 ->
            "Mất kết nối. $pendingSyncCount thao tác đang chờ đồng bộ."
        !isOnline -> "Mất kết nối. Ứng dụng đang dùng dữ liệu đã lưu."
        else -> "$pendingSyncCount thao tác đang chờ đồng bộ."
    }
    Row(
        modifier = modifier
            .fillMaxWidth()
            .background(extras.warningTint)
            .padding(horizontal = 16.dp, vertical = 8.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        Icon(
            imageVector = if (isOnline) Icons.Filled.Sync else Icons.Filled.CloudOff,
            contentDescription = null,
            tint = extras.warning,
        )
        Text(
            text = text,
            color = extras.warning,
            style = MaterialTheme.typography.labelMedium,
        )
    }
}
