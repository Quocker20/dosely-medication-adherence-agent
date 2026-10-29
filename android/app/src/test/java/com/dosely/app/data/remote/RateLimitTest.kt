package com.dosely.app.data.remote

import java.io.IOException
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.ResponseBody.Companion.toResponseBody
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test
import retrofit2.HttpException
import retrofit2.Response

class RateLimitTest {
    private fun http(code: Int, body: String): HttpException = HttpException(
        Response.error<Any>(code, body.toResponseBody("application/json".toMediaType())),
    )

    private fun body(message: String, retryAfter: Int?) = buildString {
        append("""{"success":false,"code":429,"message":"$message","data":null,"errors":""")
        append(if (retryAfter == null) "null" else """{"retry_after_seconds":$retryAfter}""")
        append("}")
    }

    @Test
    fun `lockout 429 exposes the server message and retry_after_seconds`() {
        val lock = "Bạn đã nhập sai quá nhiều lần. Vui lòng thử lại sau 15 phút."
        val limit = http(429, body(lock, 900)).loginRateLimit()

        assertEquals(lock, limit?.message)
        assertEquals(900, limit?.seconds)
    }

    @Test
    fun `per-IP login 429 gets its own Vietnamese text`() {
        val limit = http(429, body("Quá 10 yêu cầu / 60s cho login.", 30)).loginRateLimit()

        assertEquals(30, limit?.seconds)
        assertEquals("Bạn thao tác quá nhanh, vui lòng thử lại sau 30 giây.", limit?.message)
    }

    @Test
    fun `non 429 errors are not rate limits`() {
        assertNull(http(401, body("x", null)).loginRateLimit())
        assertNull(IOException("down").loginRateLimit())
        assertNull(http(500, "not json").chatRateLimitMessage())
    }

    @Test
    fun `429 with unreadable body still reports a rate limit`() {
        val limit = http(429, "<html>").loginRateLimit()

        assertEquals(0, limit?.seconds)
        assertEquals("Bạn thao tác quá nhanh, vui lòng thử lại sau 60 giây.", limit?.message)
    }

    @Test
    fun `chat daily limit message is shown verbatim`() {
        val daily = "Bạn đã dùng hết lượt hỏi trợ lý hôm nay, vui lòng quay lại vào ngày mai."

        assertEquals(daily, http(429, body(daily, 3600)).chatRateLimitMessage())
    }

    @Test
    fun `chat per-minute 429 shows the slow-down text`() {
        assertEquals(
            "Bạn gửi quá nhanh, vui lòng thử lại sau ít giây.",
            http(429, body("Quá 20 yêu cầu / 60s cho chat.", 12)).chatRateLimitMessage(),
        )
    }
}
