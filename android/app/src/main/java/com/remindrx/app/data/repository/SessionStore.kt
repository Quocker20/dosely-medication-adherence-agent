package com.remindrx.app.data.repository

import javax.inject.Inject
import javax.inject.Singleton

/**
 * Giữ access token + patientId sau khi đăng nhập, dùng chung cho mọi
 * repository (Hilt singleton) — tránh phải truyền token qua từng ViewModel.
 * Trong bộ nhớ only theo README (chưa có encrypted storage/refresh).
 */
@Singleton
class SessionStore @Inject constructor() {
    @Volatile var accessToken: String? = null
        private set

    @Volatile var patientId: String? = null
        private set

    fun update(accessToken: String, patientId: String) {
        this.accessToken = accessToken
        this.patientId = patientId
    }

    fun clear() {
        accessToken = null
        patientId = null
    }

    fun requirePatientId(): String =
        patientId ?: error("Chưa đăng nhập: không có patientId trong phiên làm việc.")
}
