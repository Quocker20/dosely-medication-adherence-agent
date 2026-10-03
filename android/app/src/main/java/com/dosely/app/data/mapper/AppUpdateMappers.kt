package com.dosely.app.data.mapper

import com.dosely.app.data.AppUpdateInfo
import com.dosely.app.data.remote.LatestAppVersionDto

fun LatestAppVersionDto.toDomain(): AppUpdateInfo = AppUpdateInfo(
    versionCode = versionCode,
    versionName = versionName,
    downloadUrl = downloadUrl,
)
