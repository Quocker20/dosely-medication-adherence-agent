package com.remindrx.app.ui.feature.patient

import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Shape
import androidx.compose.ui.text.TextRange
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.TextFieldValue

private const val ROUTINE_TIME_DIGIT_COUNT = 4

/**
 * Numeric routine-time input that formats values as HH:mm without losing the
 * cursor position when the parent updates its state.
 */
@Composable
internal fun RoutineTimeField(
    time: String,
    onTimeChanged: (String) -> Unit,
    modifier: Modifier,
    shape: Shape,
    textStyle: TextStyle,
) {
    var fieldValue by remember {
        mutableStateOf(normalizeRoutineTimeInput(TextFieldValue(time)))
    }

    // The routine can be refreshed from the server independently of typing.
    // Avoid overwriting the local selection for the value just entered.
    LaunchedEffect(time) {
        if (fieldValue.text != time) {
            fieldValue = normalizeRoutineTimeInput(TextFieldValue(time))
        }
    }

    OutlinedTextField(
        value = fieldValue,
        onValueChange = { enteredValue ->
            val normalizedValue = normalizeRoutineTimeInput(enteredValue)
            fieldValue = normalizedValue
            onTimeChanged(normalizedValue.text)
        },
        modifier = modifier,
        shape = shape,
        textStyle = textStyle,
        placeholder = { Text("HH:mm") },
        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
        isError = fieldValue.text.length == 5 && !fieldValue.text.isValidRoutineTime(),
        singleLine = true,
    )
}

/**
 * Keeps only four digits, formats them as HH:mm, and maps the selection by the
 * number of digits before it. Mapping selection instead of only the text keeps
 * consecutive digit input in its intended order after the colon is inserted.
 */
internal fun normalizeRoutineTimeInput(value: TextFieldValue): TextFieldValue {
    val digits = value.text.filter(Char::isDigit).take(ROUTINE_TIME_DIGIT_COUNT)
    val formattedText = if (digits.length <= 2) digits else "${digits.take(2)}:${digits.drop(2)}"

    fun displayOffset(offset: Int): Int {
        val digitCount = value.text
            .take(offset.coerceIn(0, value.text.length))
            .count(Char::isDigit)
            .coerceAtMost(digits.length)
        return (if (digitCount <= 2) digitCount else digitCount + 1).coerceAtMost(formattedText.length)
    }

    return value.copy(
        text = formattedText,
        selection = TextRange(
            start = displayOffset(value.selection.start),
            end = displayOffset(value.selection.end),
        ),
    )
}

internal fun String.isValidRoutineTime(): Boolean {
    if (!matches(Regex("\\d{2}:\\d{2}"))) return false
    val (hour, minute) = split(':').map(String::toInt)
    return hour in 0..23 && minute in 0..59
}
