import { ApiError } from "../../../api";

/** Gom message đọc được từ lỗi API: ưu tiên chi tiết validation, fallback về message chung. */
export function errorLines(error: unknown): string[] {
  if (error instanceof ApiError) return error.details.length ? error.details : [error.message];
  return [error instanceof Error ? error.message : "Lỗi không xác định"];
}

export function ErrorPanel({ lines, onRetry }: { lines: string[]; onRetry: () => void }) {
  return <div className="errors"><b>Không tải được dữ liệu</b><ul>{lines.map((line, index) => <li key={index}>{line}</li>)}</ul><div><button className="btn sm" onClick={onRetry}>Thử lại</button></div></div>;
}
