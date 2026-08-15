package com.remindrx.app.ui.feature.auth

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Lock
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import com.remindrx.app.ui.components.GuardrailNote
import com.remindrx.app.ui.components.PrimaryButton
import com.remindrx.app.ui.theme.LocalRemindRxColors

@Composable
fun ChangePinScreen(
    isLoading: Boolean,
    error: String?,
    isRequired: Boolean = true,
    onInputChanged: () -> Unit,
    onChangePin: (currentPin: String, newPin: String, confirmedPin: String) -> Unit,
) {
    val extras = LocalRemindRxColors.current
    val focusManager = LocalFocusManager.current
    var currentPin by remember { mutableStateOf("") }
    var newPin by remember { mutableStateOf("") }
    var confirmedPin by remember { mutableStateOf("") }
    val canSubmit = currentPin.length == 6 && newPin.length == 6 && confirmedPin.length == 6 && !isLoading

    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(horizontal = 24.dp, vertical = 28.dp),
    ) {
        Icon(
            Icons.Filled.Lock,
            contentDescription = null,
            tint = MaterialTheme.colorScheme.primary,
            modifier = Modifier.padding(bottom = 18.dp),
        )
        Text(
            if (isRequired) "Tạo mã PIN mới" else "Đổi mã PIN",
            style = MaterialTheme.typography.headlineMedium,
        )
        Text(
            if (isRequired) {
                "Để bảo vệ thông tin sức khoẻ, bạn cần đổi mã PIN do bác sĩ hoặc quản trị viên cung cấp trước khi tiếp tục."
            } else {
                "Tạo mã PIN mới gồm 6 chữ số. Bạn sẽ dùng mã này cho lần đăng nhập tiếp theo."
            },
            style = MaterialTheme.typography.bodyMedium,
            color = extras.inkMuted,
            modifier = Modifier.padding(top = 8.dp, bottom = 24.dp),
        )

        Text(
            "Mã PIN hiện tại",
            style = MaterialTheme.typography.labelMedium,
            color = extras.inkMuted,
            modifier = Modifier.padding(bottom = 8.dp),
        )
        OutlinedTextField(
            value = currentPin,
            onValueChange = { value ->
                currentPin = value.filter(Char::isDigit).take(6)
                onInputChanged()
            },
            modifier = Modifier.fillMaxWidth(),
            shape = RoundedCornerShape(14.dp),
            placeholder = { Text("Nhập 6 chữ số hiện tại") },
            visualTransformation = PasswordVisualTransformation(),
            keyboardOptions = KeyboardOptions(
                keyboardType = KeyboardType.NumberPassword,
                imeAction = ImeAction.Next,
            ),
            isError = error != null,
            singleLine = true,
        )

        Text(
            "Mã PIN mới",
            style = MaterialTheme.typography.labelMedium,
            color = extras.inkMuted,
            modifier = Modifier.padding(top = 18.dp, bottom = 8.dp),
        )
        OutlinedTextField(
            value = newPin,
            onValueChange = { value ->
                newPin = value.filter(Char::isDigit).take(6)
                onInputChanged()
            },
            modifier = Modifier.fillMaxWidth(),
            shape = RoundedCornerShape(14.dp),
            placeholder = { Text("Nhập 6 chữ số") },
            visualTransformation = PasswordVisualTransformation(),
            keyboardOptions = KeyboardOptions(
                keyboardType = KeyboardType.NumberPassword,
                imeAction = ImeAction.Next,
            ),
            isError = error != null,
            singleLine = true,
        )

        Text(
            "Nhập lại mã PIN mới",
            style = MaterialTheme.typography.labelMedium,
            color = extras.inkMuted,
            modifier = Modifier.padding(top = 18.dp, bottom = 8.dp),
        )
        OutlinedTextField(
            value = confirmedPin,
            onValueChange = { value ->
                confirmedPin = value.filter(Char::isDigit).take(6)
                onInputChanged()
            },
            modifier = Modifier.fillMaxWidth(),
            shape = RoundedCornerShape(14.dp),
            placeholder = { Text("Nhập lại 6 chữ số") },
            visualTransformation = PasswordVisualTransformation(),
            keyboardOptions = KeyboardOptions(
                keyboardType = KeyboardType.NumberPassword,
                imeAction = ImeAction.Done,
            ),
            keyboardActions = KeyboardActions(
                onDone = {
                    focusManager.clearFocus()
                    if (canSubmit) onChangePin(currentPin, newPin, confirmedPin)
                },
            ),
            isError = error != null,
            singleLine = true,
        )

        if (error != null) {
            Text(
                error,
                style = MaterialTheme.typography.bodyMedium,
                color = extras.danger,
                modifier = Modifier.padding(top = 12.dp),
            )
        }

        GuardrailNote(
            "Mã PIN phải có đúng 6 chữ số và khác mã PIN hiện tại.",
            modifier = Modifier.fillMaxWidth().padding(top = 20.dp),
        )

        PrimaryButton(
            text = if (isLoading) {
                "Đang lưu…"
            } else if (isRequired) {
                "Đổi mã PIN & tiếp tục"
            } else {
                "Lưu mã PIN mới"
            },
            onClick = {
                focusManager.clearFocus()
                onChangePin(currentPin, newPin, confirmedPin)
            },
            modifier = Modifier.fillMaxWidth().padding(top = 24.dp),
            enabled = canSubmit,
        )
    }
}

@com.remindrx.app.ui.preview.RemindRxScreenPreview
@Composable
private fun ChangePinScreenPreview() = com.remindrx.app.ui.preview.RemindRxPreview {
    ChangePinScreen(
        isLoading = false,
        error = null,
        isRequired = true,
        onInputChanged = {},
        onChangePin = { _, _, _ -> },
    )
}
