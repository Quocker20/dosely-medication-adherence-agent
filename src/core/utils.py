import re

def clean_phone_number(phone: str) -> str:
    """
    Clean and validate Vietnam phone number to standard E.164 (+84xxxxxxxx).
    Supports inputs: '0987654321', '84987654321', '+84987654321', '098 765 4321'
    """
    if not phone:
        raise ValueError("Phone number cannot be empty")

    # 1. Remove all spaces, hyphens, dots and keep only digits or '+'
    cleaned = re.sub(r"[^\d+]", "", phone.strip())

    # 2. Convert different prefix formats to standard +84
    if cleaned.startswith("0"):
        cleaned = "+84" + cleaned[1:]
    elif cleaned.startswith("84"):
        cleaned = "+" + cleaned
    elif not cleaned.startswith("+84"):
        cleaned = "+84" + cleaned

    # 3. Validate using regex for current Vietnam mobile prefixes (3, 5, 7, 8, 9 + 8 digits)
    # Total length of standard E.164 string is 12 characters (including '+')
    if not re.match(r"^\+84[35789]\d{8}$", cleaned):
        raise ValueError("Invalid Vietnam mobile phone number format")

    return cleaned