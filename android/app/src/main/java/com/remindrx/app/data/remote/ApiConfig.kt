package com.remindrx.app.data.remote

object ApiConfig {
    // 10.0.2.2 là cách emulator Android truy cập localhost của máy host.
    // Thiết bị thật cần đổi sang IP LAN của máy host hoặc URL đã deploy.
    const val BASE_URL = "http://10.0.2.2:8000/api/v1/"
}
