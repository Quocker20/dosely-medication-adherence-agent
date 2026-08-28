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

## Tải app Android để test

`public/try/index.html` là trang tải file APK demo (build từ `android/`, đã
trỏ sẵn vào backend công khai) để cài trực tiếp lên điện thoại Android. Xem
[docs/android-app-testing.md](../docs/android-app-testing.md) để build APK và
đưa file lên server.

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

## Deploy lên production (Vercel)

Domain chính thức duy nhất: **https://p-216.vercel.app** (project `p-216`, scope
`pro-vjp`). Không tạo thêm domain khác — mỗi lần `vercel --prod` tự alias vào
đúng domain này vì nó đã được đăng ký chính thức cho project (`vercel domains
add`), không cần set alias tay.

### Deploy

```bash
cd web
npx vercel --prod
```

Cần đã `npx vercel login` và project đã link (`web/.vercel/` tồn tại — nếu máy
mới chưa link, chạy `npx vercel link --yes --project p-216 --scope pro-vjp`
trước).

Sau khi deploy xong, verify:

```bash
curl -s https://p-216.vercel.app/api/health   # phải trả JSON từ backend (404 vì route thật là /health, không phải /api/health — vậy là bình thường)
curl -sI https://p-216.vercel.app/doctor/     # phải 200 (SPA fallback, không phải file thật)
```

### `vercel.json` — vì sao có 3 rule

```json
{
  "rewrites": [
    { "source": "/api/:path*", "destination": "https://<tunnel-hoac-domain-backend>/api/:path*" },
    { "source": "/downloads/:path*", "destination": "https://<tunnel-hoac-domain-backend>/downloads/:path*" },
    { "source": "/((?!api/|downloads/).*)", "destination": "/index.html" }
  ]
}
```

- 2 rule đầu: proxy API/downloads sang backend FastAPI (VPS `remindrx.duckdns.org`,
  hiện đi qua Cloudflare Tunnel — xem mục dưới).
- Rule cuối: SPA fallback — app không dùng router thật (xem `src/app/App.tsx`),
  path như `/doctor/`, `/admin/`, `/patient/` không phải file thật, cần fallback
  về `index.html` để React tự xử lý, nếu không sẽ 404 khi mở link trực tiếp/refresh.

### ⚠️ Backend hiện chưa có IPv4 public ổn định

VPS (`192.168.0.101` nội bộ) không có IPv4 public riêng, domain
`remindrx.duckdns.org` chỉ resolve ra IPv6 — **Vercel Rewrites không hỗ trợ
destination IPv6-only** (`DNS_HOSTNAME_EMPTY`). Đường vòng qua NPM/FossVPS
(`202.us2.0em.org`) đang bị lỗi platform (self-redirect 308) chưa sửa được.

Giải pháp tạm: **Cloudflare Quick Tunnel** chạy trên VPS qua systemd
(`/etc/systemd/system/cloudflared.service`, `Restart=always`, đã enable).
Nhược điểm: mỗi lần service này restart (crash, VPS reboot...) sẽ sinh ra
**URL random mới**, phải cập nhật lại `vercel.json` thủ công.

**Khi web portal báo lỗi API (404/502 lạ, không phải `/health` 404 bình thường), làm theo runbook sau — trên VPS:**

```bash
# 1. Kiểm tra cloudflared còn sống không, lấy URL hiện tại
systemctl status cloudflared
journalctl -u cloudflared -n 50 --no-pager | grep trycloudflare
```

Rồi ở máy dev (thư mục `web/`):

```bash
# 2. Sửa URL tunnel mới vào cả 2 chỗ trong vercel.json (destination /api và /downloads)
# 3. Deploy lại
npx vercel --prod
# 4. Verify
curl -s https://p-216.vercel.app/api/health
```

Giải pháp lâu dài (khi có domain riêng): chuyển sang **Cloudflare Named
Tunnel** gắn domain cố định — không còn bị đổi URL nữa. Chưa làm vì hiện chưa
có domain riêng (domain của dự án hiện chỉ có DuckDNS free, không add được vào
Cloudflare).

### Rollback

Vào https://vercel.com/pro-vjp/p-216 → tab Deployments → chọn bản cũ (status
Ready) → bấm nút "Production" ở dòng đó để promote lại tức thì, không cần
deploy lại.

## Ràng buộc UI phải giữ

- Nút duyệt đơn gọi đúng chuỗi `POST /prescriptions` → `/approve` → `/schedules/generate`.
  Không có đường nào tạo lịch từ đơn `DRAFT`.
- Lỗi 422 từ validator hiển thị nguyên văn danh sách issue, không rút gọn thành
  "có lỗi" — bác sĩ cần biết sai ở dòng nào.
- Lịch trạng thái `NEEDS_REVIEW` phải hiện review note; không được ẩn đi để giao
  diện trông "sạch".
- Không thêm nút nào cho phép sửa liều sau khi đơn đã `APPROVED`.
