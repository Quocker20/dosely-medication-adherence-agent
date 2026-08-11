package com.remindrx.app.ui.theme

import androidx.compose.material3.Typography
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.sp

// Sizes run above Material3 defaults on purpose — primary audience is elderly
// patients, legibility beats density everywhere in this app.
val RemindRxTypography = Typography(
    headlineLarge = TextStyle(fontWeight = FontWeight.ExtraBold, fontSize = 28.sp, lineHeight = 34.sp),
    headlineMedium = TextStyle(fontWeight = FontWeight.ExtraBold, fontSize = 24.sp, lineHeight = 30.sp),
    titleLarge = TextStyle(fontWeight = FontWeight.Bold, fontSize = 20.sp, lineHeight = 26.sp),
    titleMedium = TextStyle(fontWeight = FontWeight.Bold, fontSize = 17.sp, lineHeight = 22.sp),
    bodyLarge = TextStyle(fontWeight = FontWeight.Normal, fontSize = 18.sp, lineHeight = 26.sp),
    bodyMedium = TextStyle(fontWeight = FontWeight.Normal, fontSize = 16.sp, lineHeight = 23.sp),
    labelLarge = TextStyle(fontWeight = FontWeight.Bold, fontSize = 16.sp, lineHeight = 20.sp),
    labelMedium = TextStyle(fontWeight = FontWeight.Bold, fontSize = 13.sp, lineHeight = 17.sp),
    labelSmall = TextStyle(fontWeight = FontWeight.SemiBold, fontSize = 11.sp, lineHeight = 14.sp),
)
