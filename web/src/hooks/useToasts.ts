import { useCallback, useState } from "react";

export interface ToastItem {
  id: number;
  text: string;
}

/**
 * Hàng đợi thông báo tự ẩn. Mỗi toast tự xoá sau `durationMs`, không phụ thuộc
 * các toast khác — nên bắn liên tiếp nhiều toast vẫn đúng thứ tự hết hạn.
 *
 * Doctor portal dùng 2600ms, Admin/Patient dùng mặc định 2800ms — giữ nguyên
 * đúng giá trị của từng nơi trước khi gộp hook, đừng "chuẩn hoá" thành một số.
 */
export function useToasts(durationMs = 2800) {
  const [toasts, setToasts] = useState<ToastItem[]>([]);

  const notify = useCallback(
    (text: string) => {
      const id = Date.now() + Math.random();
      setToasts((current) => [...current, { id, text }]);
      window.setTimeout(
        () => setToasts((current) => current.filter((item) => item.id !== id)),
        durationMs,
      );
    },
    [durationMs],
  );

  return { toasts, notify };
}
