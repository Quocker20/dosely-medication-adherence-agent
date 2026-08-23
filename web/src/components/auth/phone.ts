export interface PhoneValidationResult {
  ok: boolean;
  cleaned: string | null;
  error: string | null;
}

const VN_PHONE_REGEX = /^\+84[35789]\d{8}$/;
const INVALID_PHONE_MESSAGE = "Số điện thoại không đúng định dạng (VD: 0901234567)";

/** Mirrors the backend's clean_phone_number normalization and validation. */
export function cleanPhoneNumber(raw: string): PhoneValidationResult {
  let cleaned = raw.trim().replace(/[^\d+]/g, "");

  if (cleaned.startsWith("0")) {
    cleaned = `+84${cleaned.slice(1)}`;
  } else if (cleaned.startsWith("84")) {
    cleaned = `+${cleaned}`;
  } else if (!cleaned.startsWith("+84")) {
    cleaned = `+84${cleaned}`;
  }

  return VN_PHONE_REGEX.test(cleaned)
    ? { ok: true, cleaned, error: null }
    : { ok: false, cleaned: null, error: INVALID_PHONE_MESSAGE };
}
