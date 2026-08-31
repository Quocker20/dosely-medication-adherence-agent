package com.remindrx.app.ui.feature.assistant

import android.Manifest
import android.content.pm.PackageManager
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.automirrored.filled.Send
import androidx.compose.material.icons.filled.Menu
import androidx.compose.material.icons.filled.Mic
import androidx.compose.material.icons.filled.SmartToy
import androidx.compose.material.icons.filled.Stop
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.IconButtonDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.platform.LocalInspectionMode
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import com.remindrx.app.data.ChatMessage
import com.remindrx.app.data.ChatRole
import com.remindrx.app.ui.theme.LocalRemindRxColors

@Composable
fun AssistantScreen(
    state: AssistantUiState,
    onSend: (String) -> Unit,
    onOpenHistory: () -> Unit,
    onBack: (() -> Unit)? = null,
    onStartRecording: () -> Unit = {},
    onStopRecordingAndSend: () -> Unit = {},
) {
    val extras = LocalRemindRxColors.current
    val listState = rememberLazyListState()
    val focusManager = LocalFocusManager.current
    var input by remember { mutableStateOf("") }
    val context = LocalContext.current
    val isPreview = LocalInspectionMode.current
    val micPermissionLauncher = if (isPreview) {
        null
    } else {
        rememberLauncherForActivityResult(
            ActivityResultContracts.RequestPermission(),
        ) { granted -> if (granted) onStartRecording() }
    }

    LaunchedEffect(state.messages.size, state.isReplying) {
        val lastIndex = state.messages.lastIndex + if (state.isReplying) 1 else 0
        if (lastIndex >= 0) listState.animateScrollToItem(lastIndex)
    }

    Column(Modifier.fillMaxSize()) {
        Row(
            modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 10.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            if (onBack != null) {
                IconButton(onClick = onBack) {
                    Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Quay lại")
                }
            }
            Icon(
                Icons.Filled.SmartToy,
                contentDescription = null,
                tint = extras.ai,
                modifier = Modifier.padding(end = 10.dp),
            )
            Column(Modifier.weight(1f)) {
                Text("Trợ lý AI", style = MaterialTheme.typography.titleLarge)
                Text(
                    "Thuốc & lịch uống · Demo",
                    style = MaterialTheme.typography.labelMedium,
                    color = extras.inkMuted,
                    fontWeight = FontWeight.Normal,
                )
            }
            IconButton(onClick = onOpenHistory) {
                Icon(Icons.Filled.Menu, contentDescription = "Lịch sử Chat AI")
            }
        }

        LazyColumn(
            state = listState,
            modifier = Modifier.weight(1f).fillMaxWidth(),
            contentPadding = PaddingValues(horizontal = 16.dp, vertical = 8.dp),
            verticalArrangement = Arrangement.spacedBy(9.dp),
        ) {
            item {
                Card(
                    shape = RoundedCornerShape(12.dp),
                    colors = CardDefaults.cardColors(containerColor = extras.warningTint),
                    modifier = Modifier.fillMaxWidth().padding(bottom = 4.dp),
                ) {
                    Text(
                        "AI chỉ cung cấp thông tin tham khảo; không tự thay đổi liều hoặc xử trí cấp cứu theo chat.",
                        style = MaterialTheme.typography.labelMedium,
                        color = extras.warning,
                        fontWeight = FontWeight.Normal,
                        modifier = Modifier.padding(10.dp),
                    )
                }
            }
            items(state.messages, key = ChatMessage::id) { message ->
                ChatBubble(message)
            }
            if (state.isReplying) {
                item {
                    Row(
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.spacedBy(8.dp),
                        modifier = Modifier.padding(10.dp),
                    ) {
                        CircularProgressIndicator(modifier = Modifier.size(18.dp), strokeWidth = 2.dp)
                        Text("Đang tra cứu…", style = MaterialTheme.typography.labelMedium, color = extras.inkMuted)
                    }
                }
            }
            if (state.error != null) {
                item {
                    Card(
                        shape = RoundedCornerShape(12.dp),
                        colors = CardDefaults.cardColors(containerColor = extras.dangerTint),
                        modifier = Modifier.fillMaxWidth().padding(vertical = 4.dp),
                    ) {
                        Text(
                            state.error,
                            style = MaterialTheme.typography.labelMedium,
                            color = extras.danger,
                            fontWeight = FontWeight.Normal,
                            modifier = Modifier.padding(10.dp),
                        )
                    }
                }
            }
        }

        Row(
            modifier = Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 8.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            OutlinedTextField(
                value = input,
                onValueChange = { input = it },
                modifier = Modifier.weight(1f),
                shape = RoundedCornerShape(20.dp),
                enabled = !state.isRecording,
                placeholder = {
                    Text(if (state.isRecording) "Đang ghi âm…" else "Hỏi về thuốc hoặc lịch uống…")
                },
                keyboardOptions = KeyboardOptions(imeAction = ImeAction.Send),
                keyboardActions = KeyboardActions(
                    onSend = {
                        if (input.isNotBlank() && !state.isReplying) {
                            onSend(input)
                            input = ""
                            focusManager.clearFocus()
                        }
                    },
                ),
                maxLines = 4,
            )
            IconButton(
                onClick = {
                    when {
                        state.isRecording -> onStopRecordingAndSend()
                        ContextCompat.checkSelfPermission(
                            context,
                            Manifest.permission.RECORD_AUDIO,
                        ) == PackageManager.PERMISSION_GRANTED -> onStartRecording()
                        else -> micPermissionLauncher?.launch(Manifest.permission.RECORD_AUDIO)
                    }
                },
                enabled = !state.isReplying,
                colors = if (state.isRecording) {
                    IconButtonDefaults.iconButtonColors(containerColor = extras.dangerTint)
                } else {
                    IconButtonDefaults.iconButtonColors()
                },
            ) {
                Icon(
                    if (state.isRecording) Icons.Filled.Stop else Icons.Filled.Mic,
                    contentDescription = if (state.isRecording) "Dừng ghi âm và gửi" else "Hỏi bằng giọng nói",
                    tint = if (state.isRecording) extras.danger else extras.ai,
                )
            }
            IconButton(
                onClick = {
                    onSend(input)
                    input = ""
                    focusManager.clearFocus()
                },
                enabled = input.isNotBlank() && !state.isReplying && !state.isRecording,
            ) {
                Icon(Icons.AutoMirrored.Filled.Send, contentDescription = "Gửi", tint = extras.ai)
            }
        }
    }
}

@Composable
private fun ChatBubble(message: ChatMessage) {
    val extras = LocalRemindRxColors.current
    val isUser = message.role == ChatRole.USER
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = if (isUser) Arrangement.End else Arrangement.Start,
    ) {
        Card(
            shape = RoundedCornerShape(
                topStart = 18.dp,
                topEnd = 18.dp,
                bottomStart = if (isUser) 18.dp else 4.dp,
                bottomEnd = if (isUser) 4.dp else 18.dp,
            ),
            colors = CardDefaults.cardColors(
                containerColor = if (isUser) extras.ai else extras.surfaceAlt,
            ),
            modifier = Modifier.widthIn(max = 320.dp),
        ) {
            Column(Modifier.padding(horizontal = 13.dp, vertical = 10.dp)) {
                Text(
                    message.content,
                    style = MaterialTheme.typography.bodyMedium,
                    color = if (isUser) MaterialTheme.colorScheme.onPrimary else MaterialTheme.colorScheme.onSurface,
                )
                Text(
                    message.time,
                    style = MaterialTheme.typography.labelSmall,
                    color = if (isUser) {
                        MaterialTheme.colorScheme.onPrimary.copy(alpha = 0.72f)
                    } else {
                        extras.inkMuted
                    },
                    modifier = Modifier.padding(top = 4.dp).align(Alignment.End),
                )
            }
        }
    }
}

@com.remindrx.app.ui.preview.RemindRxScreenPreview
@Composable
private fun AssistantScreenPreview() = com.remindrx.app.ui.preview.RemindRxPreview {
    AssistantScreen(
        state = com.remindrx.app.ui.preview.previewAssistantState,
        onSend = {},
        onOpenHistory = {},
    )
}
