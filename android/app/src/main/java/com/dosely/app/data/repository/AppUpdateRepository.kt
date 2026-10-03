package com.dosely.app.data.repository

import com.dosely.app.data.AppUpdateInfo

/** Reads public release metadata once when the application process starts. */
interface AppUpdateRepository {
    suspend fun getLatestVersion(): AppUpdateInfo
}
