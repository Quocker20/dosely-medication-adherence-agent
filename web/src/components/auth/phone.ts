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

/**
 * Chuẩn hóa chuỗi tìm kiếm trước khi gửi lên API query param `search`.
 * Nếu người dùng gõ số điện thoại bắt đầu bằng 0 (VD: 0901234567, 090...),
 * hàm sẽ chuyển đổi thành dạng +84... để khớp với định dạng E.164 trong Database.
 */
export function normalizeSearchQuery(raw: string): string {
  const trimmed = raw.trim();
  if (!trimmed) return "";

  const digitsOnly = trimmed.replace(/[\s.-]/g, "");
  if (/^0\d+$/.test(digitsOnly)) {
    return `+84${digitsOnly.slice(1)}`;
  }
  if (/^84\d+$/.test(digitsOnly)) {
    return `+${digitsOnly}`;
  }

  return trimmed;
}
