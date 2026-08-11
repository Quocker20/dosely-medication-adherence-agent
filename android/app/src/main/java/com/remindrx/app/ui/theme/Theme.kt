package com.remindrx.app.ui.theme

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.graphics.Color

// Material3's ColorScheme has no adherence-status slots (taken/late/missed),
// so those semantic tokens travel through their own CompositionLocal instead
// of being smuggled into unrelated Material roles.
data class RemindRxColors(
    val surfaceAlt: Color,
    val border: Color,
    val inkMuted: Color,
    val primaryTint: Color,
    val success: Color,
    val successTint: Color,
    val warning: Color,
    val warningTint: Color,
    val danger: Color,
    val dangerTint: Color,
)

private val LightExtras = RemindRxColors(
    surfaceAlt = LightSurfaceAlt,
    border = LightBorder,
    inkMuted = LightInkMuted,
    primaryTint = LightPrimaryTint,
    success = LightSuccess,
    successTint = LightSuccessTint,
    warning = LightWarning,
    warningTint = LightWarningTint,
    danger = LightDanger,
    dangerTint = LightDangerTint,
)

private val DarkExtras = RemindRxColors(
    surfaceAlt = DarkSurfaceAlt,
    border = DarkBorder,
    inkMuted = DarkInkMuted,
    primaryTint = DarkPrimaryTint,
    success = DarkSuccess,
    successTint = DarkSuccessTint,
    warning = DarkWarning,
    warningTint = DarkWarningTint,
    danger = DarkDanger,
    dangerTint = DarkDangerTint,
)

val LocalRemindRxColors = staticCompositionLocalOf { LightExtras }

@Composable
fun RemindRxTheme(
    darkTheme: Boolean = isSystemInDarkTheme(),
    content: @Composable () -> Unit,
) {
    val scheme = if (darkTheme) {
        darkColorScheme(
            primary = DarkPrimary,
            onPrimary = DarkBg,
            secondary = DarkPrimaryDark,
            background = DarkBg,
            surface = DarkSurface,
            onBackground = DarkInk,
            onSurface = DarkInk,
            outline = DarkBorder,
        )
    } else {
        lightColorScheme(
            primary = LightPrimary,
            onPrimary = Color.White,
            secondary = LightPrimaryDark,
            background = LightBg,
            surface = LightSurface,
            onBackground = LightInk,
            onSurface = LightInk,
            outline = LightBorder,
        )
    }
    val extras = if (darkTheme) DarkExtras else LightExtras

    CompositionLocalProvider(LocalRemindRxColors provides extras) {
        MaterialTheme(
            colorScheme = scheme,
            typography = RemindRxTypography,
            content = content,
        )
    }
}
