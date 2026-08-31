package com.remindrx.app.data.repository

import com.remindrx.app.data.AppUpdateInfo

/** Reads public release metadata once when the application process starts. */
interface AppUpdateRepository {
    suspend fun getLatestVersion(): AppUpdateInfo
}
