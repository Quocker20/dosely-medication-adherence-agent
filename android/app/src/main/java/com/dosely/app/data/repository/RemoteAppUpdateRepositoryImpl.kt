package com.dosely.app.data.repository

import com.dosely.app.data.AppUpdateInfo
import com.dosely.app.data.mapper.toDomain
import com.dosely.app.data.remote.DoselyApiService
import com.dosely.app.data.remote.requireData
import javax.inject.Inject

class RemoteAppUpdateRepositoryImpl @Inject constructor(
    private val api: DoselyApiService,
) : AppUpdateRepository {
    override suspend fun getLatestVersion(): AppUpdateInfo = api
        .getLatestAppVersion()
        .requireData("Kiểm tra bản cập nhật")
        .toDomain()
}
