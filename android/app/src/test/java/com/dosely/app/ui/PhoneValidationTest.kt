package com.dosely.app.ui

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class PhoneValidationTest {
    @Test
    fun `valid Vietnamese mobile numbers normalize to E164`() {
        listOf("0901234567", "84901234567", "+84901234567").forEach { raw ->
            val result = validateVnPhone(raw)
            assertTrue(result.ok)
            assertEquals("+84901234567", result.cleaned)
            assertNull(result.error)
        }
    }

    @Test
    fun `invalid Vietnamese mobile numbers return an inline error`() {
        listOf("", "0201234567", "0901234").forEach { raw ->
            val result = validateVnPhone(raw)
            assertFalse(result.ok)
            assertNull(result.cleaned)
            assertEquals("Số điện thoại không đúng định dạng (VD: 0901234567)", result.error)
        }
    }
}
