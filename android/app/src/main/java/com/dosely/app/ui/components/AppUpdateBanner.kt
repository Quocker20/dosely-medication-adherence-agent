package com.dosely.app.ui.components

import android.content.Intent
import android.net.Uri
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.SystemUpdate
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.dosely.app.data.AppUpdateInfo
import com.dosely.app.ui.theme.LocalDoselyColors

@Composable
fun AppUpdateBanner(
    update: AppUpdateInfo,
    onUpdate: (String) -> Unit,
    onDismiss: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val extras = LocalDoselyColors.current
    Row(
        modifier = modifier
            .fillMaxWidth()
            .background(extras.primaryTint)
            .padding(horizontal = 16.dp, vertical = 8.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        Icon(
            imageVector = Icons.Filled.SystemUpdate,
            contentDescription = null,
            tint = MaterialTheme.colorScheme.primary,
        )
        Column(modifier = Modifier.weight(1f)) {
            Text(
                text = "Có bản cập nhật Dosely",
                color = MaterialTheme.colorScheme.primary,
                style = MaterialTheme.typography.labelLarge,
            )
            Text(
                text = "Phiên bản ${update.versionName} đã sẵn sàng.",
                color = MaterialTheme.colorScheme.primary,
                style = MaterialTheme.typography.bodySmall,
            )
            TextButton(onClick = { onUpdate(update.downloadUrl) }) {
                Text("Cập nhật")
            }
        }
        IconButton(onClick = onDismiss) {
            Icon(
                imageVector = Icons.Filled.Close,
                contentDescription = "Đóng thông báo cập nhật",
                tint = MaterialTheme.colorScheme.primary,
            )
        }
    }
}

/**
 * Opens the APK in a browser; Android installation remains a user action.
 *
 * TODO(SEC-11): [AppUpdateInfo.sha256] is carried through but cannot be checked here -
 * the download happens in the external browser/DownloadManager, outside the app's
 * control. Verifying the hash before install requires downloading in-app (e.g.
 * DownloadManager + MessageDigest, then installing from our own FileProvider URI).
 */
fun createAppUpdateIntent(downloadUrl: String): Intent = Intent(
    Intent.ACTION_VIEW,
    Uri.parse(downloadUrl),
).addCategory(Intent.CATEGORY_BROWSABLE)
