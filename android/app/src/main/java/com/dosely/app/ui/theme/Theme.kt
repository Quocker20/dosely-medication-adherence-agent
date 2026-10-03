package com.dosely.app.ui.theme

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
data class DoselyColors(
    val brand: Color,
    val surfaceAlt: Color,
    val border: Color,
    val inkMuted: Color,
    val primaryTint: Color,
    val secondaryTint: Color,
    val ai: Color,
    val aiTint: Color,
    val success: Color,
    val successTint: Color,
    val warning: Color,
    val warningTint: Color,
    val danger: Color,
    val dangerStrong: Color,
    val dangerTint: Color,
)

private val LightExtras = DoselyColors(
    brand = LightBrandBlue,
    surfaceAlt = LightSurfaceAlt,
    border = LightBorder,
    inkMuted = LightInkMuted,
    primaryTint = LightPrimaryTint,
    secondaryTint = LightSecondaryTint,
    ai = LightAi,
    aiTint = LightAiTint,
    success = LightSuccess,
    successTint = LightSuccessTint,
    warning = LightWarning,
    warningTint = LightWarningTint,
    danger = LightDanger,
    dangerStrong = LightDangerStrong,
    dangerTint = LightDangerTint,
)

private val DarkExtras = DoselyColors(
    brand = DarkBrandBlue,
    surfaceAlt = DarkSurfaceAlt,
    border = DarkBorder,
    inkMuted = DarkInkMuted,
    primaryTint = DarkPrimaryTint,
    secondaryTint = DarkSecondaryTint,
    ai = DarkAi,
    aiTint = DarkAiTint,
    success = DarkSuccess,
    successTint = DarkSuccessTint,
    warning = DarkWarning,
    warningTint = DarkWarningTint,
    danger = DarkDanger,
    dangerStrong = DarkDangerStrong,
    dangerTint = DarkDangerTint,
)

val LocalDoselyColors = staticCompositionLocalOf { LightExtras }

@Composable
fun DoselyTheme(
    darkTheme: Boolean = isSystemInDarkTheme(),
    content: @Composable () -> Unit,
) {
    val scheme = if (darkTheme) {
        darkColorScheme(
            primary = DarkPrimary,
            onPrimary = DarkOnPrimary,
            primaryContainer = DarkPrimaryTint,
            onPrimaryContainer = DarkInk,
            secondary = DarkSecondary,
            secondaryContainer = DarkSecondaryTint,
            onSecondaryContainer = DarkInk,
            tertiary = DarkTertiary,
            tertiaryContainer = DarkTertiaryTint,
            onTertiaryContainer = DarkInk,
            error = DarkDanger,
            errorContainer = DarkDangerTint,
            background = DarkBg,
            surface = DarkSurface,
            onBackground = DarkInk,
            onSurface = DarkInk,
            outline = DarkBorder,
            outlineVariant = DarkBorder,
        )
    } else {
        lightColorScheme(
            primary = LightPrimary,
            onPrimary = LightOnPrimary,
            primaryContainer = LightPrimaryTint,
            onPrimaryContainer = LightInk,
            secondary = LightSecondary,
            secondaryContainer = LightSecondaryTint,
            onSecondaryContainer = LightInk,
            tertiary = LightTertiary,
            tertiaryContainer = LightTertiaryTint,
            onTertiaryContainer = LightInk,
            error = LightDanger,
            errorContainer = LightDangerTint,
            background = LightBg,
            surface = LightSurface,
            onBackground = LightInk,
            onSurface = LightInk,
            outline = LightBorder,
            outlineVariant = LightBorder,
        )
    }
    val extras = if (darkTheme) DarkExtras else LightExtras

    CompositionLocalProvider(LocalDoselyColors provides extras) {
        MaterialTheme(
            colorScheme = scheme,
            typography = DoselyTypography,
            content = content,
        )
    }
}
