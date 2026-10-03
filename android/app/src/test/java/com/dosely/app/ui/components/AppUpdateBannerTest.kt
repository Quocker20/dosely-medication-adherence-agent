package com.dosely.app.ui.components

import android.content.Intent
import android.net.Uri
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner

@RunWith(RobolectricTestRunner::class)
class AppUpdateBannerTest {
    @Test
    fun `update action opens the exact APK URI in a browsable intent`() {
        val downloadUrl = "https://api.example.test/downloads/dosely-demo.apk"

        val intent = createAppUpdateIntent(downloadUrl)

        assertEquals(Intent.ACTION_VIEW, intent.action)
        assertEquals(Uri.parse(downloadUrl), intent.data)
        assertTrue(intent.categories?.contains(Intent.CATEGORY_BROWSABLE) == true)
    }
}
