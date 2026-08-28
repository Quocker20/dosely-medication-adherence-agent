package com.remindrx.app.ui.feature.patient

import androidx.compose.ui.text.TextRange
import androidx.compose.ui.text.input.TextFieldValue
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class RoutineTimeFieldTest {

    @Test
    fun `replacing selected minutes keeps consecutive digits in order`() {
        val afterFirstDigit = normalizeRoutineTimeInput(
            TextFieldValue(text = "06:5", selection = TextRange(4)),
        )
        val afterSecondDigit = normalizeRoutineTimeInput(
            TextFieldValue(text = "06:59", selection = TextRange(5)),
        )

        assertEquals("06:5", afterFirstDigit.text)
        assertEquals(TextRange(4), afterFirstDigit.selection)
        assertEquals("06:59", afterSecondDigit.text)
        assertEquals(TextRange(5), afterSecondDigit.selection)
    }

    @Test
    fun `pasting digits inserts colon and moves cursor past it`() {
        val formatted = normalizeRoutineTimeInput(
            TextFieldValue(text = "0659", selection = TextRange(4)),
        )

        assertEquals("06:59", formatted.text)
        assertEquals(TextRange(5), formatted.selection)
    }

    @Test
    fun `deleting colon preserves position before minutes`() {
        val formatted = normalizeRoutineTimeInput(
            TextFieldValue(text = "0634", selection = TextRange(2)),
        )

        assertEquals("06:34", formatted.text)
        assertEquals(TextRange(2), formatted.selection)
    }

    @Test
    fun `input is limited to four digits`() {
        val formatted = normalizeRoutineTimeInput(
            TextFieldValue(text = "12345", selection = TextRange(5)),
        )

        assertEquals("12:34", formatted.text)
        assertEquals(TextRange(5), formatted.selection)
    }

    @Test
    fun `validation accepts valid day bounds and rejects invalid times`() {
        assertTrue("00:00".isValidRoutineTime())
        assertTrue("23:59".isValidRoutineTime())
        assertFalse("24:00".isValidRoutineTime())
        assertFalse("12:60".isValidRoutineTime())
        assertFalse("9:30".isValidRoutineTime())
    }
}
