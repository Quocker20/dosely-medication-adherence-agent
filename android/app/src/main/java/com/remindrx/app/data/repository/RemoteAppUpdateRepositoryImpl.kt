package com.remindrx.app.data.repository

import com.remindrx.app.data.AppUpdateInfo
import com.remindrx.app.data.mapper.toDomain
import com.remindrx.app.data.remote.RemindRxApiService
import com.remindrx.app.data.remote.requireData
import javax.inject.Inject

class RemoteAppUpdateRepositoryImpl @Inject constructor(
    private val api: RemindRxApiService,
) : AppUpdateRepository {
    override suspend fun getLatestVersion(): AppUpdateInfo = api
        .getLatestAppVersion()
        .requireData("Kiểm tra bản cập nhật")
        .toDomain()
}
