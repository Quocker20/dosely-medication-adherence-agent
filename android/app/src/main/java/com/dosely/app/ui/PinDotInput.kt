package com.dosely.app.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import com.dosely.app.ui.theme.LocalDoselyColors

@Composable
fun PinDotInput(
    value: String,
    onValueChange: (String) -> Unit,
    modifier: Modifier = Modifier,
    length: Int = 6,
    enabled: Boolean = true,
) {
    val extras = LocalDoselyColors.current
    val focusRequester = remember { FocusRequester() }

    Box(
        modifier = modifier
            .fillMaxWidth()
            .height(40.dp)
            .clickable(enabled = enabled) { focusRequester.requestFocus() },
        contentAlignment = Alignment.Center,
    ) {
        BasicTextField(
            value = value,
            onValueChange = { onValueChange(it.filter(Char::isDigit).take(length)) },
            modifier = Modifier.fillMaxSize().alpha(0f).focusRequester(focusRequester),
            enabled = enabled,
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.NumberPassword),
            singleLine = true,
        )
        Row(horizontalArrangement = Arrangement.spacedBy(14.dp)) {
            repeat(length) { index ->
                val filled = index < value.length
                Box(
                    modifier = Modifier
                        .size(16.dp)
                        .background(if (filled) extras.brand else Color.Transparent, CircleShape)
                        .border(if (filled) 0.dp else 1.5.dp, if (filled) Color.Transparent else extras.border, CircleShape),
                )
            }
        }
    }
}
