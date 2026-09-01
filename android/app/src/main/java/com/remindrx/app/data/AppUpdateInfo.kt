package com.remindrx.app.data

/** A newer APK that the user may choose to open and install manually. */
data class AppUpdateInfo(
    val versionCode: Int,
    val versionName: String,
    val downloadUrl: String,
)
