package com.remindrx.app.ui.screens

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
import com.remindrx.app.data.MockRepository
import com.remindrx.app.ui.theme.LocalRemindRxColors
import kotlinx.coroutines.delay

private const val HOLD_MILLIS = 3000

/**
 * Hold-to-confirm is deliberate: a plain tap SOS button is a false-alarm
 * risk for patients with reduced dexterity. 3s matches the mockup spec.
 */
@Composable
fun SosScreen(onTriggered: () -> Unit, onCancel: () -> Unit) {
    val extras = LocalRemindRxColors.current
    var pressed by remember { mutableStateOf(false) }
    var triggered by remember { mutableStateOf(false) }
    val progress by animateFloatAsState(
        targetValue = if (pressed && !triggered) 1f else 0f,
        animationSpec = if (pressed) tween(HOLD_MILLIS, easing = LinearEasing) else tween(150),
        label = "sos-hold",
    )

    LaunchedEffect(pressed) {
        if (pressed) {
            delay(HOLD_MILLIS.toLong())
            triggered = true
        }
    }

    LaunchedEffect(triggered) {
        if (triggered) onTriggered()
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
                    .pointerInput(triggered) {
                        if (!triggered) {
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
                            if (triggered) "ĐANG GỌI" else "SOS",
                            style = MaterialTheme.typography.headlineMedium,
                            color = extras.danger,
                        )
                        Text(
                            if (triggered) "Chị Hoa..." else "GIỮ ĐỂ GỌI",
                            style = MaterialTheme.typography.labelSmall,
                            color = extras.danger,
                            fontWeight = FontWeight.Bold,
                        )
                    }
                }
            }

            Text(
                if (triggered) "Đang gọi khẩn cấp và gửi vị trí" else "Giữ nút 3 giây để gọi khẩn cấp",
                style = MaterialTheme.typography.titleMedium,
                color = Color.White,
                textAlign = TextAlign.Center,
                modifier = Modifier.padding(top = 20.dp),
            )
            Text(
                "Sẽ gọi: ${MockRepository.emergencyContact.name} (${MockRepository.emergencyContact.relation})\nkèm vị trí hiện tại của bạn",
                style = MaterialTheme.typography.bodyMedium,
                color = Color.White.copy(alpha = 0.9f),
                textAlign = TextAlign.Center,
                fontWeight = FontWeight.Normal,
                modifier = Modifier.padding(top = 6.dp),
            )
            Text(
                "Huỷ",
                style = MaterialTheme.typography.labelLarge,
                color = Color.White,
                modifier = Modifier
                    .padding(top = 14.dp)
                    .pointerInput(Unit) { detectTapGestures(onTap = { onCancel() }) },
            )
        }
    }
}
