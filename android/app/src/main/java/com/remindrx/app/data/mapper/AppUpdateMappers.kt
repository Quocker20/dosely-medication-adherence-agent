package com.remindrx.app.data.mapper

import com.remindrx.app.data.AppUpdateInfo
import com.remindrx.app.data.remote.LatestAppVersionDto

fun LatestAppVersionDto.toDomain(): AppUpdateInfo = AppUpdateInfo(
    versionCode = versionCode,
    versionName = versionName,
    downloadUrl = downloadUrl,
)
