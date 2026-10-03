package com.dosely.app.data.remote

import com.google.gson.annotations.SerializedName

/** Public payload returned by GET /api/v1/app/latest-version. */
data class LatestAppVersionDto(
    @SerializedName("versionCode")
    val versionCode: Int,
    @SerializedName("versionName")
    val versionName: String,
    @SerializedName("downloadUrl")
    val downloadUrl: String,
)
