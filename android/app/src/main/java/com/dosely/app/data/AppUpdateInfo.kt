package com.dosely.app.data

/** A newer APK that the user may choose to open and install manually. */
data class AppUpdateInfo(
    val versionCode: Int,
    val versionName: String,
    val downloadUrl: String,
    /** Hex SHA-256 of the APK as published by the backend; null when it could not be computed. */
    val sha256: String? = null,
)
