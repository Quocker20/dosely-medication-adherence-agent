// Part of src/types/ — xem index.ts cho ràng buộc sync với backend.
// Envelope chung (src/core/response.py:APIResponse)

/** Mọi endpoint REST đều bọc payload trong envelope này, kể cả khi lỗi. */
export interface ApiEnvelope<T> {
  success: boolean;
  code: number;
  message: string;
  data: T | null;
  errors?: unknown;
}

/** Wrapper phân trang chuẩn (src/common/schemas.py:PageResponse). */
export interface PageResponse<T> {
  content: T[];
  page_no: number;
  page_size: number;
  total_elements: number;
  total_pages: number;
  last: boolean;
}
