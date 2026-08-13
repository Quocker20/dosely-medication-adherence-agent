package com.remindrx.app.ui

import java.io.IOException
import java.net.ConnectException
import java.net.SocketTimeoutException
import java.net.UnknownHostException

/** Prevent low-level network messages (host, port, socket details) leaking into the UI. */
fun Throwable.toVietnameseUiMessage(fallback: String): String {
    val rawMessage = message.orEmpty()
    val isConnectionError = this is ConnectException ||
        this is UnknownHostException ||
        this is SocketTimeoutException ||
        this is IOException ||
        rawMessage.contains("failed to connect", ignoreCase = true) ||
        rawMessage.contains("connection refused", ignoreCase = true) ||
        rawMessage.contains("unable to resolve host", ignoreCase = true) ||
        rawMessage.contains("timeout", ignoreCase = true)

    return if (isConnectionError) {
        "Không thể kết nối đến máy chủ RemindRx. Vui lòng kiểm tra kết nối mạng và thử lại sau."
    } else {
        fallback
    }
}
