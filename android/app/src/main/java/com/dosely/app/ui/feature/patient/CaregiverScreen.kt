package com.dosely.app.ui.feature.patient

import android.content.Intent
import android.net.Uri
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
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.automirrored.filled.Send
import androidx.compose.material.icons.filled.DeleteOutline
import androidx.compose.material.icons.filled.People
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import com.dosely.app.ui.components.ChipTone
import com.dosely.app.ui.components.PrimaryButton
import com.dosely.app.ui.components.DoselyPullRefresh
import com.dosely.app.ui.components.StatusChip
import com.dosely.app.ui.theme.LocalDoselyColors

data class CaregiverInviteUi(
    val linkCode: String,
    val telegramDeepLink: String?,
)

data class CaregiverUi(
    val linkId: String,
    val relationship: String?,
    val phone: String? = null,
    val status: String,
    val linkCode: String? = null,
    val telegramDeepLink: String? = null,
)

@Composable
fun CaregiverScreen(
    caregivers: List<CaregiverUi>,
    isLoading: Boolean,
    isAdding: Boolean,
    deletingLinkId: String?,
    error: String?,
    createdInvite: CaregiverInviteUi?,
    onBack: () -> Unit,
    onRetry: () -> Unit,
    onInputChanged: () -> Unit,
    onAdd: (phone: String, relationship: String?) -> Unit,
    onDelete: (linkId: String) -> Unit,
) {
    val extras = LocalDoselyColors.current
    val context = LocalContext.current
    var phone by remember { mutableStateOf("") }
    var relationship by remember { mutableStateOf("") }
    var submittedAdd by remember { mutableStateOf(false) }
    var pendingDelete by remember { mutableStateOf<CaregiverUi?>(null) }
    val normalizedPhone = phone.trim().replace(" ", "")
    val canAdd = normalizedPhone.matches(Regex("^\\+?[0-9]{9,15}$")) && !isAdding

    LaunchedEffect(isAdding, error) {
        if (isAdding) submittedAdd = true
        if (submittedAdd && !isAdding && error == null) {
            phone = ""
            relationship = ""
            submittedAdd = false
        }
    }

    pendingDelete?.let { caregiver ->
        AlertDialog(
            onDismissRequest = { pendingDelete = null },
            title = { Text("Gỡ người chăm sóc?") },
            text = { Text("Người thân này sẽ không còn nhận được thông báo về tình trạng sức khỏe của bạn.") },
            confirmButton = {
                TextButton(
                    onClick = {
                        onDelete(caregiver.linkId)
                        pendingDelete = null
                    },
                ) {
                    Text("Gỡ liên kết", color = extras.danger)
                }
            },
            dismissButton = {
                TextButton(onClick = { pendingDelete = null }) { Text("Huỷ") }
            },
        )
    }

    DoselyPullRefresh(isRefreshing = isLoading, onRefresh = onRetry) {
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
                    Text("Người chăm sóc", style = MaterialTheme.typography.headlineMedium)
                }
            }

            item {
                Text(
                    "Liên kết người thân để nhận thông báo khẩn cấp và báo cáo tuân thủ dùng thuốc qua Telegram Bot.",
                    style = MaterialTheme.typography.bodyMedium,
                    color = extras.inkMuted,
                )
            }

            item {
                Text(
                    "💡 3 bước đơn giản: 1. Điền SĐT người thân ➔ 2. Nhận link Telegram ➔ 3. Gửi cho người thân bấm START để kích hoạt.",
                    style = MaterialTheme.typography.labelMedium,
                    color = MaterialTheme.colorScheme.primary,
                    fontWeight = FontWeight.SemiBold,
                )
            }

            item {
                Card(
                    modifier = Modifier.fillMaxWidth(),
                    shape = RoundedCornerShape(16.dp),
                    colors = CardDefaults.cardColors(containerColor = extras.surfaceAlt),
                ) {
                    Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                        Text("Thêm người chăm sóc", style = MaterialTheme.typography.titleMedium)
                        OutlinedTextField(
                            value = phone,
                            onValueChange = {
                                phone = it.take(16)
                                onInputChanged()
                            },
                            modifier = Modifier.fillMaxWidth(),
                            label = { Text("Số điện thoại") },
                            placeholder = { Text("Ví dụ: 0901234567") },
                            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Phone),
                            singleLine = true,
                        )
                        OutlinedTextField(
                            value = relationship,
                            onValueChange = {
                                relationship = it.take(50)
                                onInputChanged()
                            },
                            modifier = Modifier.fillMaxWidth(),
                            label = { Text("Mối quan hệ (không bắt buộc)") },
                            placeholder = { Text("Ví dụ: Con gái") },
                            singleLine = true,
                        )
                        PrimaryButton(
                            text = if (isAdding) "Đang tạo liên kết…" else "Thêm người chăm sóc",
                            onClick = {
                                onAdd(
                                    normalizedPhone,
                                    relationship.trim().takeIf(String::isNotEmpty),
                                )
                            },
                            modifier = Modifier.fillMaxWidth(),
                            enabled = canAdd,
                        )
                    }
                }
            }

            createdInvite?.let { invite ->
                item {
                    Card(
                        modifier = Modifier.fillMaxWidth(),
                        shape = RoundedCornerShape(16.dp),
                        colors = CardDefaults.cardColors(containerColor = extras.primaryTint),
                        border = BorderStroke(1.dp, MaterialTheme.colorScheme.primary.copy(alpha = 0.3f)),
                    ) {
                        Column(
                            modifier = Modifier.padding(16.dp),
                            verticalArrangement = Arrangement.spacedBy(10.dp),
                        ) {
                            Row(
                                verticalAlignment = Alignment.CenterVertically,
                                horizontalArrangement = Arrangement.spacedBy(8.dp),
                            ) {
                                Icon(
                                    Icons.AutoMirrored.Filled.Send,
                                    contentDescription = null,
                                    tint = MaterialTheme.colorScheme.primary,
                                )
                                Text(
                                    "Mã liên kết Telegram",
                                    style = MaterialTheme.typography.titleMedium,
                                    color = MaterialTheme.colorScheme.primary,
                                )
                            }
                            Text(
                                invite.linkCode,
                                style = MaterialTheme.typography.headlineLarge,
                                fontWeight = FontWeight.Bold,
                                color = MaterialTheme.colorScheme.primary,
                            )
                            Text(
                                "Chia sẻ liên kết này với người thân. Người thân chỉ cần mở link và bấm START trên Telegram để kích hoạt nhận thông báo.",
                                style = MaterialTheme.typography.bodySmall,
                                color = extras.inkMuted,
                            )
                            invite.telegramDeepLink?.let { deepLink ->
                                Row(
                                    modifier = Modifier.fillMaxWidth().padding(top = 4.dp),
                                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                                ) {
                                    PrimaryButton(
                                        text = "Mở Telegram",
                                        onClick = {
                                            val intent = Intent(Intent.ACTION_VIEW, Uri.parse(deepLink))
                                            context.startActivity(intent)
                                        },
                                        modifier = Modifier.weight(1f),
                                    )
                                    OutlinedButton(
                                        onClick = {
                                            val sendIntent = Intent().apply {
                                                action = Intent.ACTION_SEND
                                                putExtra(
                                                    Intent.EXTRA_TEXT,
                                                    "Hãy tham gia làm người giám hộ chăm sóc sức khỏe của tôi trên Dosely qua link: $deepLink",
                                                )
                                                type = "text/plain"
                                            }
                                            context.startActivity(Intent.createChooser(sendIntent, "Chia sẻ link Telegram"))
                                        },
                                        modifier = Modifier.weight(1f),
                                    ) {
                                        Text("Chia sẻ link")
                                    }
                                }
                            }
                        }
                    }
                }
            }

            error?.let { message ->
                item {
                    Column(Modifier.fillMaxWidth(), horizontalAlignment = Alignment.CenterHorizontally) {
                        Text(message, style = MaterialTheme.typography.bodyMedium, color = extras.danger)
                        TextButton(onClick = onRetry) { Text("Thử tải lại") }
                    }
                }
            }

            item {
                Text("Đã liên kết", style = MaterialTheme.typography.titleMedium, modifier = Modifier.padding(top = 4.dp))
            }

            when {
                isLoading -> item {
                    Row(Modifier.fillMaxWidth().padding(24.dp), horizontalArrangement = Arrangement.Center) {
                        CircularProgressIndicator()
                    }
                }

                caregivers.isEmpty() -> item {
                    Text(
                        "Chưa có người chăm sóc nào được liên kết.",
                        style = MaterialTheme.typography.bodyMedium,
                        color = extras.inkMuted,
                        modifier = Modifier.padding(vertical = 14.dp),
                    )
                }

                else -> items(caregivers, key = CaregiverUi::linkId) { caregiver ->
                    CaregiverRow(
                        caregiver = caregiver,
                        isDeleting = deletingLinkId == caregiver.linkId,
                        onDelete = { pendingDelete = caregiver },
                    )
                }
            }
        }
    }
}

@Composable
private fun CaregiverRow(caregiver: CaregiverUi, isDeleting: Boolean, onDelete: () -> Unit) {
    val extras = LocalDoselyColors.current
    Card(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(14.dp),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
        border = BorderStroke(1.dp, extras.border),
    ) {
        Row(
            modifier = Modifier.fillMaxWidth().padding(14.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Icon(Icons.Filled.People, contentDescription = null, tint = MaterialTheme.colorScheme.primary)
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Row(
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    Text(
                        caregiver.relationship?.takeIf(String::isNotBlank) ?: "Người chăm sóc",
                        style = MaterialTheme.typography.titleMedium,
                    )
                    StatusChip(
                        text = when (caregiver.status) {
                            "ACTIVE" -> "Đang hoạt động"
                            "BLOCKED" -> "Đã chặn bot"
                            else -> "Chờ kết nối"
                        },
                        tone = when (caregiver.status) {
                            "ACTIVE" -> ChipTone.SUCCESS
                            "BLOCKED" -> ChipTone.DANGER
                            else -> ChipTone.WARNING
                        },
                    )
                }
                Text(
                    caregiver.phone?.takeIf(String::isNotBlank) ?: "Tài khoản đã liên kết",
                    style = MaterialTheme.typography.labelMedium,
                    color = extras.inkMuted,
                    fontWeight = FontWeight.Normal,
                )
                Text(
                    "Kênh: Telegram Bot",
                    style = MaterialTheme.typography.labelSmall,
                    color = extras.inkMuted,
                )
            }
            if (isDeleting) {
                CircularProgressIndicator(modifier = Modifier.padding(8.dp))
            } else {
                IconButton(onClick = onDelete) {
                    Icon(Icons.Filled.DeleteOutline, contentDescription = "Gỡ liên kết", tint = extras.danger)
                }
            }
        }
    }
}

@com.dosely.app.ui.preview.DoselyScreenPreview
@Composable
private fun CaregiverScreenPreview() = com.dosely.app.ui.preview.DoselyPreview {
    CaregiverScreen(
        caregivers = com.dosely.app.ui.preview.previewCaregivers,
        isLoading = false,
        isAdding = false,
        deletingLinkId = null,
        error = null,
        createdInvite = CaregiverInviteUi(
            linkCode = "AB12CD",
            telegramDeepLink = "https://t.me/Dosely_bot?start=AB12CD",
        ),
        onBack = {},
        onRetry = {},
        onInputChanged = {},
        onAdd = { _, _ -> },
        onDelete = {},
    )
}
