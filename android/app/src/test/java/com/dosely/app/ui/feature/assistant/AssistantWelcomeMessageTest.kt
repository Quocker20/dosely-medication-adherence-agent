package com.dosely.app.ui.feature.assistant

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class AssistantWelcomeMessageTest {
    @Test
    fun `welcome is neutral before patient profile is loaded`() {
        val content = welcomeMessage().content

        assertTrue(content.startsWith("Chào bạn!"))
        assertFalse(content.contains("Chào bác"))
        assertFalse(content.contains("Bác muốn"))
    }
}
