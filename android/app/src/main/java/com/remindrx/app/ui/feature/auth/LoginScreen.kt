package com.remindrx.app.ui.feature.auth

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.LocalHospital
import androidx.compose.material.icons.filled.Shield
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import com.remindrx.app.ui.components.PrimaryButton
import com.remindrx.app.ui.theme.LocalRemindRxColors

@Composable
fun LoginScreen(
    isLoading: Boolean,
    error: String?,
    onInputChanged: () -> Unit,
    onLogin: (phone: String, pin: String) -> Unit,
) {
    val extras = LocalRemindRxColors.current
    val focusManager = LocalFocusManager.current
    var phone by remember { mutableStateOf("") }
    var pin by remember { mutableStateOf("") }
    val canSubmit = phone.isNotBlank() && pin.length == 6 && !isLoading

    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(horizontal = 24.dp),
    ) {
        Column(
            modifier = Modifier.fillMaxWidth().padding(top = 40.dp, bottom = 28.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            Card(
                shape = RoundedCornerShape(18.dp),
                colors = CardDefaults.cardColors(containerColor = extras.brand),
                modifier = Modifier.size(64.dp),
            ) {
                Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                    Icon(
                        Icons.Filled.LocalHospital,
                        contentDescription = null,
                        tint = Color.White,
                        modifier = Modifier.size(30.dp),
                    )
                }
            }
            Spacer(Modifier.height(14.dp))
            Text("RemindRx", style = MaterialTheme.typography.headlineMedium)
            Text(
                "Bạn uống thuốc, chúng tôi nhắc giờ",
                style = MaterialTheme.typography.bodyMedium,
                color = extras.inkMuted,
                textAlign = TextAlign.Center,
            )
        }

        Text("Đăng nhập", style = MaterialTheme.typography.headlineMedium)
        Text(
            "Dùng số điện thoại và mã PIN 6 chữ số của bạn.",
            style = MaterialTheme.typography.bodyMedium,
            color = extras.inkMuted,
            modifier = Modifier.padding(top = 4.dp, bottom = 22.dp),
        )

        Text(
            "Số điện thoại",
            style = MaterialTheme.typography.labelMedium,
            color = extras.inkMuted,
            modifier = Modifier.padding(bottom = 8.dp),
        )
        OutlinedTextField(
            value = phone,
            onValueChange = { value ->
                phone = value.filter { it.isDigit() || it == '+' }.take(16)
                onInputChanged()
            },
            modifier = Modifier.fillMaxWidth().padding(bottom = 18.dp),
            shape = RoundedCornerShape(14.dp),
            textStyle = MaterialTheme.typography.bodyLarge,
            placeholder = { Text("Nhập số điện thoại") },
            keyboardOptions = KeyboardOptions(
                keyboardType = KeyboardType.Phone,
                imeAction = ImeAction.Next,
            ),
            singleLine = true,
        )

        Text(
            "Mã PIN",
            style = MaterialTheme.typography.labelMedium,
            color = extras.inkMuted,
            modifier = Modifier.padding(bottom = 8.dp),
        )
        OutlinedTextField(
            value = pin,
            onValueChange = { value ->
                pin = value.filter(Char::isDigit).take(6)
                onInputChanged()
            },
            modifier = Modifier.fillMaxWidth(),
            shape = RoundedCornerShape(14.dp),
            textStyle = MaterialTheme.typography.bodyLarge,
            placeholder = { Text("6 chữ số") },
            visualTransformation = PasswordVisualTransformation(),
            keyboardOptions = KeyboardOptions(
                keyboardType = KeyboardType.NumberPassword,
                imeAction = ImeAction.Done,
            ),
            keyboardActions = KeyboardActions(
                onDone = {
                    focusManager.clearFocus()
                    if (canSubmit) onLogin(phone, pin)
                },
            ),
            isError = error != null,
            singleLine = true,
        )

        Text(
            "Nếu đây là lần đăng nhập đầu tiên, mã PIN ban đầu do bác sĩ hoặc quản trị viên cung cấp.",
            style = MaterialTheme.typography.labelMedium,
            color = extras.inkMuted,
            fontWeight = FontWeight.Normal,
            modifier = Modifier.padding(top = 8.dp),
        )

        if (error != null) {
            Text(
                error,
                style = MaterialTheme.typography.bodyMedium,
                color = extras.danger,
                modifier = Modifier.padding(top = 12.dp),
            )
        }

        PrimaryButton(
            text = if (isLoading) "Đang đăng nhập…" else "Đăng nhập",
            onClick = {
                focusManager.clearFocus()
                onLogin(phone, pin)
            },
            modifier = Modifier.fillMaxWidth().padding(top = 20.dp),
            enabled = canSubmit,
        )

        Row(
            modifier = Modifier.fillMaxWidth().weight(1f).padding(top = 24.dp),
            horizontalArrangement = Arrangement.Center,
            verticalAlignment = Alignment.Bottom,
        ) {
            Row(
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(8.dp),
                modifier = Modifier.padding(bottom = 24.dp),
            ) {
                Icon(
                    Icons.Filled.Shield,
                    contentDescription = null,
                    tint = extras.inkMuted,
                    modifier = Modifier.size(15.dp),
                )
                Text(
                    "Đơn thuốc do bác sĩ duyệt · dữ liệu mã hoá",
                    style = MaterialTheme.typography.labelSmall,
                    color = extras.inkMuted,
                    fontWeight = FontWeight.Normal,
                )
            }
        }
    }
}

@com.remindrx.app.ui.preview.RemindRxScreenPreview
@Composable
private fun LoginScreenPreview() = com.remindrx.app.ui.preview.RemindRxPreview {
    LoginScreen(
        isLoading = false,
        error = null,
        onInputChanged = {},
        onLogin = { _, _ -> },
    )
}
