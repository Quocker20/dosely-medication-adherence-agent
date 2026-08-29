package com.remindrx.app.ui.feature.patient

import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.tween
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import com.remindrx.app.ui.theme.LocalRemindRxColors
import kotlinx.coroutines.delay

private const val HOLD_MILLIS = 3000

/**
 * Holding avoids accidental SOS events. The screen only reports the state of
 * the backend alert; it does not imply a phone call, GPS sharing, or direct
 * delivery to a relative.
 */
@Composable
fun SosScreen(
    sosStatus: SosSubmissionStatus = SosSubmissionStatus.IDLE,
    error: String? = null,
    onTriggered: () -> Unit,
    onCancel: () -> Unit,
) {
    val extras = LocalRemindRxColors.current
    var pressed by remember { mutableStateOf(false) }
    var requested by remember { mutableStateOf(false) }
    val isSending = sosStatus == SosSubmissionStatus.SENDING
    val isSent = sosStatus == SosSubmissionStatus.SENT
    val isQueuedOffline = sosStatus == SosSubmissionStatus.QUEUED_OFFLINE
    val canTrigger = !requested && (sosStatus == SosSubmissionStatus.IDLE || sosStatus == SosSubmissionStatus.FAILED)
    val progress by animateFloatAsState(
        targetValue = if (pressed && canTrigger) 1f else 0f,
        animationSpec = if (pressed) tween(HOLD_MILLIS, easing = LinearEasing) else tween(150),
        label = "sos-hold",
    )

    LaunchedEffect(pressed, canTrigger) {
        if (pressed && canTrigger) {
            delay(HOLD_MILLIS.toLong())
            if (pressed) {
                requested = true
                pressed = false
                onTriggered()
            }
        }
    }

    LaunchedEffect(error) {
        if (error != null) requested = false
    }

    Box(
        modifier = Modifier
            .fillMaxSize()
            .background(Brush.verticalGradient(listOf(extras.danger, extras.dangerStrong))),
    ) {
        Column(
            modifier = Modifier.fillMaxSize().padding(24.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.Center,
        ) {
            Box(
                modifier = Modifier
                    .size(168.dp)
                    .background(Color.White.copy(alpha = 0.14f), CircleShape)
                    .padding(23.dp)
                    .pointerInput(canTrigger) {
                        if (canTrigger) {
                            detectTapGestures(
                                onPress = {
                                    pressed = true
                                    tryAwaitRelease()
                                    pressed = false
                                },
                            )
                        }
                    },
                contentAlignment = Alignment.Center,
            ) {
                Canvas(Modifier.fillMaxSize()) {
                    drawArc(
                        color = Color.White,
                        startAngle = -90f,
                        sweepAngle = 360f * progress,
                        useCenter = false,
                        style = Stroke(width = 4.dp.toPx()),
                        size = Size(size.width, size.height),
                    )
                }
                Box(
                    modifier = Modifier
                        .fillMaxSize()
                        .padding(10.dp)
                        .background(Color.White, CircleShape),
                    contentAlignment = Alignment.Center,
                ) {
                    Column(horizontalAlignment = Alignment.CenterHorizontally) {
                        Text(
                            when {
                                isSent -> "ĐÃ GỬI"
                                isQueuedOffline -> "ĐÃ LƯU"
                                requested || isSending -> "ĐANG GỬI"
                                else -> "SOS"
                            },
                            style = MaterialTheme.typography.headlineMedium,
                            color = extras.danger,
                        )
                        Text(
                            when {
                                isSent -> "CẢNH BÁO SOS"
                                isQueuedOffline -> "CHỜ CÓ MẠNG"
                                requested || isSending -> "VUI LÒNG ĐỢI"
                                else -> "GIỮ ĐỂ GỬI"
                            },
                            style = MaterialTheme.typography.labelSmall,
                            color = extras.danger,
                            fontWeight = FontWeight.Bold,
                        )
                    }
                }
            }

            Text(
                when {
                    isSent -> "Cảnh báo SOS đã được gửi tới hệ thống"
                    isQueuedOffline -> "Yêu cầu SOS đã lưu trên máy nhưng chưa gửi được"
                    requested || isSending -> "Đang gửi cảnh báo SOS…"
                    else -> "Giữ nút 3 giây để gửi cảnh báo SOS"
                },
                style = MaterialTheme.typography.titleMedium,
                color = Color.White,
                textAlign = TextAlign.Center,
                modifier = Modifier.padding(top = 20.dp),
            )
            Text(
                if (isQueuedOffline) {
                    "Nếu đang khẩn cấp, hãy gọi 115 ngay. Ứng dụng sẽ đồng bộ yêu cầu này khi có mạng."
                } else if (isSent) {
                    "Hệ thống đã ghi nhận cảnh báo. Ứng dụng không tự gọi cấp cứu hoặc chia sẻ vị trí."
                } else {
                    "Yêu cầu sẽ được chuyển tới hệ thống chăm sóc sau khi bạn xác nhận."
                },
                style = MaterialTheme.typography.bodyMedium,
                color = Color.White.copy(alpha = 0.9f),
                textAlign = TextAlign.Center,
                fontWeight = FontWeight.Normal,
                modifier = Modifier.padding(top = 6.dp),
            )
            error?.let {
                Text(
                    it,
                    style = MaterialTheme.typography.labelMedium,
                    color = Color.White,
                    textAlign = TextAlign.Center,
                    fontWeight = FontWeight.Bold,
                    modifier = Modifier.padding(top = 10.dp),
                )
            }
            Text(
                if (isSent || isQueuedOffline) "Đóng" else "Huỷ",
                style = MaterialTheme.typography.labelLarge,
                color = Color.White,
                modifier = Modifier
                    .padding(top = 14.dp)
                    .pointerInput(Unit) { detectTapGestures(onTap = { onCancel() }) },
            )
        }
    }
}

@com.remindrx.app.ui.preview.RemindRxScreenPreview
@Composable
private fun SosScreenPreview() = com.remindrx.app.ui.preview.RemindRxPreview {
    SosScreen(onTriggered = {}, onCancel = {})
}
