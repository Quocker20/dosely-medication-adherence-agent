# RemindRx — Portal Bác sĩ (frontend)

React + Vite + TypeScript. Hai màn chính theo FR-1.1 (kê đơn điện tử) và FR-1.2
(dashboard tuân thủ & cảnh báo), cộng màn Red Alert của FR-4.2.

## Chạy khi dev

Cần backend chạy trước ở cổng 8000 — Vite proxy `/api` sang đó.

```bash
make run
```

```bash
cd web && npm install && npm run dev
```

Mở http://localhost:5173.

## Build cho production

```bash
cd web && npm run build
```

`web/dist/` được `src/main.py` tự mount vào `/` khi tồn tại, nên sau khi build
thì chỉ cần chạy backend là có cả UI ở http://localhost:8000.

## Cấu trúc

```
src/
├── api.ts               # client gọi /api/v1, giữ nguyên issue của validator
├── types.ts             # mirror của src/models/clinical.py
├── App.tsx              # điều hướng 3 view, load dữ liệu, toast, drawer
├── lib/labels.ts        # nhãn tiếng Việt + ngưỡng màu tuân thủ
└── components/
    ├── Sidebar.tsx          # điều hướng + badge cảnh báo + chọn theme
    ├── KpiRow.tsx           # 4 thẻ KPI đối chiếu mục tiêu MVP
    ├── PatientTable.tsx     # bảng ưu tiên + sparkline 7 ngày
    ├── PatientDrawer.tsx    # hồ sơ: lưới liều, lịch sinh hoạt, nhật ký
    ├── AlertsView.tsx       # OPEN → ACKNOWLEDGED → RESOLVED
    ├── PrescriptionView.tsx # form kê đơn, duyệt, lịch agent sinh ra
    ├── GuardBanner.tsx      # nhắc ranh giới HITL
    └── Sparkline.tsx
```

## Ràng buộc UI phải giữ

- Nút duyệt đơn gọi đúng chuỗi `POST /prescriptions` → `/approve` → `/schedules/generate`.
  Không có đường nào tạo lịch từ đơn `DRAFT`.
- Lỗi 422 từ validator hiển thị nguyên văn danh sách issue, không rút gọn thành
  "có lỗi" — bác sĩ cần biết sai ở dòng nào.
- Lịch trạng thái `NEEDS_REVIEW` phải hiện review note; không được ẩn đi để giao
  diện trông "sạch".
- Không thêm nút nào cho phép sửa liều sau khi đơn đã `APPROVED`.
