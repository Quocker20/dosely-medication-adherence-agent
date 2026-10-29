package com.dosely.app.data.mapper

import com.dosely.app.data.remote.LatestAppVersionDto
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class AppUpdateMappersTest {
    private fun dto(sha256: String?) = LatestAppVersionDto(
        versionCode = 7,
        versionName = "1.5.0",
        downloadUrl = "https://example.test/downloads/dosely-demo.apk",
        sha256 = sha256,
    )

    @Test
    fun `sha256 is carried to the domain model normalised to lower case`() {
        val info = dto("  ABCDEF0123  ").toDomain()

        assertEquals("abcdef0123", info.sha256)
        assertEquals("https://example.test/downloads/dosely-demo.apk", info.downloadUrl)
    }

    @Test
    fun `missing or blank sha256 maps to null`() {
        assertNull(dto(null).toDomain().sha256)
        assertNull(dto("   ").toDomain().sha256)
    }
}
