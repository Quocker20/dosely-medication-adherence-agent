package com.dosely.app.data.remote

import com.dosely.app.BuildConfig

object ApiConfig {
    // Cấu hình theo build type tại app/build.gradle.kts. Debug dùng 10.0.2.2
    // để vào host emulator; release chỉ chấp nhận endpoint HTTPS đã deploy.
    val BASE_URL: String = BuildConfig.API_BASE_URL
}
