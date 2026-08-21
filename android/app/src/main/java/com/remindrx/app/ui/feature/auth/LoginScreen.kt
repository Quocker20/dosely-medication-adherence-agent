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
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import com.remindrx.app.ui.PinDotInput
import com.remindrx.app.ui.components.PrimaryButton
import com.remindrx.app.ui.theme.LocalRemindRxColors
import com.remindrx.app.ui.validateVnPhone
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

private enum class LoginStep { PHONE, PIN }
private const val MIN_STEP_DELAY_MS = 400L

@Composable
fun LoginScreen(
    isLoading: Boolean,
    error: String?,
    shouldClearPin: Boolean,
    onInputChanged: () -> Unit,
    onPinCleared: () -> Unit,
    onLogin: (phone: String, pin: String) -> Unit,
) {
    val extras = LocalRemindRxColors.current
    val focusManager = LocalFocusManager.current
    val scope = rememberCoroutineScope()
    var phone by remember { mutableStateOf("") }
    var pin by remember { mutableStateOf("") }
    var step by remember { mutableStateOf(LoginStep.PHONE) }
    var isTransitioning by remember { mutableStateOf(false) }
    val phoneValidation = validateVnPhone(phone)

    LaunchedEffect(shouldClearPin) {
        if (shouldClearPin) {
            pin = ""
            onPinCleared()
        }
    }

    Column(modifier = Modifier.fillMaxSize().padding(horizontal = 24.dp)) {
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
                    Icon(Icons.Filled.LocalHospital, null, tint = Color.White, modifier = Modifier.size(30.dp))
                }
            }
            Spacer(Modifier.height(14.dp))
            Text("RemindRx", style = MaterialTheme.typography.headlineMedium)
            Text("Bạn uống thuốc, chúng tôi nhắc giờ", style = MaterialTheme.typography.bodyMedium, color = extras.inkMuted)
        }

        Text(if (step == LoginStep.PHONE) "Đăng nhập" else "Nhập mã PIN", style = MaterialTheme.typography.headlineMedium)
        Text(
            if (step == LoginStep.PHONE) "Nhập số điện thoại đã đăng ký để tiếp tục." else phone,
            style = MaterialTheme.typography.bodyMedium,
            color = extras.inkMuted,
            modifier = Modifier.padding(top = 4.dp, bottom = 22.dp),
        )

        when (step) {
            LoginStep.PHONE -> PhoneStep(
                phone = phone,
                error = error ?: phoneValidation.error.takeIf { phone.isNotEmpty() && !phoneValidation.ok },
                isTransitioning = isTransitioning,
                phoneIsValid = phoneValidation.ok,
                onPhoneChange = { value ->
                    phone = value.filter { it.isDigit() || it == '+' }.take(16)
                    onInputChanged()
                },
                onContinue = {
                    scope.launch {
                        isTransitioning = true
                        delay(MIN_STEP_DELAY_MS)
                        phone = phoneValidation.cleaned.orEmpty()
                        step = LoginStep.PIN
                        isTransitioning = false
                    }
                },
            )

            LoginStep.PIN -> PinStep(
                pin = pin,
                error = error,
                isLoading = isLoading,
                onPinChange = { pin = it; onInputChanged() },
                onLogin = { focusManager.clearFocus(); onLogin(phone, pin) },
            )
        }

        Row(
            modifier = Modifier.fillMaxWidth().weight(1f).padding(top = 24.dp, bottom = 24.dp),
            horizontalArrangement = Arrangement.Center,
            verticalAlignment = Alignment.Bottom,
        ) {
            Icon(Icons.Filled.Shield, null, tint = extras.inkMuted, modifier = Modifier.size(15.dp))
            Text(
                "Đơn thuốc do bác sĩ duyệt · dữ liệu mã hoá",
                style = MaterialTheme.typography.labelSmall,
                color = extras.inkMuted,
                modifier = Modifier.padding(start = 8.dp),
            )
        }
    }
}

@Composable
private fun PhoneStep(
    phone: String,
    error: String?,
    isTransitioning: Boolean,
    phoneIsValid: Boolean,
    onPhoneChange: (String) -> Unit,
    onContinue: () -> Unit,
) {
    val extras = LocalRemindRxColors.current
    Text("Số điện thoại", style = MaterialTheme.typography.labelMedium, color = extras.inkMuted, modifier = Modifier.padding(bottom = 8.dp))
    OutlinedTextField(
        value = phone,
        onValueChange = onPhoneChange,
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(14.dp),
        textStyle = MaterialTheme.typography.bodyLarge,
        placeholder = { Text("Nhập số điện thoại") },
        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Phone, imeAction = ImeAction.Done),
        singleLine = true,
        isError = error != null,
    )
    error?.let { LoginError(it) }
    PrimaryButton(
        text = if (isTransitioning) "Đang xử lý…" else "Tiếp tục",
        onClick = onContinue,
        modifier = Modifier.fillMaxWidth().padding(top = 20.dp),
        enabled = phoneIsValid && !isTransitioning,
    )
}

@Composable
private fun PinStep(
    pin: String,
    error: String?,
    isLoading: Boolean,
    onPinChange: (String) -> Unit,
    onLogin: () -> Unit,
) {
    val extras = LocalRemindRxColors.current
    Text("Mã PIN", style = MaterialTheme.typography.labelMedium, color = extras.inkMuted, modifier = Modifier.padding(bottom = 8.dp))
    PinDotInput(value = pin, onValueChange = onPinChange, enabled = !isLoading)
    Text("Quên mật khẩu?", style = MaterialTheme.typography.bodySmall, color = extras.brand, modifier = Modifier.padding(top = 12.dp))
    Text(
        "Nếu đây là lần đăng nhập đầu tiên, mã PIN ban đầu do bác sĩ hoặc quản trị viên cung cấp.",
        style = MaterialTheme.typography.labelMedium,
        color = extras.inkMuted,
        fontWeight = FontWeight.Normal,
        modifier = Modifier.padding(top = 8.dp),
    )
    error?.let { LoginError(it) }
    PrimaryButton(
        text = if (isLoading) "Đang đăng nhập…" else "Đăng nhập",
        onClick = onLogin,
        modifier = Modifier.fillMaxWidth().padding(top = 20.dp),
        enabled = pin.length == 6 && !isLoading,
    )
}

@Composable
private fun LoginError(message: String) {
    Text(message, style = MaterialTheme.typography.bodyMedium, color = LocalRemindRxColors.current.danger, modifier = Modifier.padding(top = 12.dp))
}

@com.remindrx.app.ui.preview.RemindRxScreenPreview
@Composable
private fun LoginScreenPreview() = com.remindrx.app.ui.preview.RemindRxPreview {
    LoginScreen(false, null, false, {}, {}, { _, _ -> })
}
