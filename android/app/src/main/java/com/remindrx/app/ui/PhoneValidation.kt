package com.remindrx.app.ui

private val VN_PHONE_REGEX = Regex("^\\+84[35789]\\d{8}$")

data class PhoneValidationResult(
    val ok: Boolean,
    val cleaned: String?,
    val error: String?,
)

/** Mirrors the backend clean_phone_number normalization and validation. */
fun validateVnPhone(raw: String): PhoneValidationResult {
    val cleaned = raw.trim().filter { it.isDigit() || it == '+' }.let {
        when {
            it.startsWith("0") -> "+84" + it.drop(1)
            it.startsWith("84") -> "+$it"
            !it.startsWith("+84") -> "+84$it"
            else -> it
        }
    }

    return if (VN_PHONE_REGEX.matches(cleaned)) {
        PhoneValidationResult(ok = true, cleaned = cleaned, error = null)
    } else {
        PhoneValidationResult(false, null, "Số điện thoại không đúng định dạng (VD: 0901234567)")
    }
}
