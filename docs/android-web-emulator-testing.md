# Thử app Android RemindRx trên web (Appetize.io)

Mục tiêu: cho người ngoài team test app Android thật của RemindRx ngay trong
trình duyệt, không cần cài Android Studio hay APK. Cách làm: build APK →
upload lên [Appetize.io](https://appetize.io) (cloud emulator) → nhúng player
của họ vào trang `web/public/emulator/index.html` bằng iframe.

App Android thật đã có sẵn ở [`android/`](../android/README.md) (Kotlin +
Compose, đã build/chạy được trên emulator cục bộ). Phần còn thiếu chỉ là build
+ upload + điền config — không cần code thêm gì trong `android/`.

## Vì sao chọn Appetize.io

- Không cần tự host emulator (Anbox/QEMU + noVNC) — nặng hạ tầng, không hợp
  với stack FastAPI hiện tại.
- Không cần tài khoản doanh nghiệp như BrowserStack/Genymotion Cloud.
- Nhúng bằng một `<iframe>` duy nhất, có free tier để demo public.

Giới hạn cần biết: free tier Appetize có giới hạn số phút sử dụng/tháng và có
thể hiện quảng cáo trên player công khai — kiểm tra gói hiện tại trên trang
pricing của họ trước khi share link cho nhiều người.

## Bước 1 — Build APK

```bash
cd android
./gradlew.bat assembleDebug
```

APK ra ở `android/app/build/outputs/apk/debug/app-debug.apk`.

Backend không cần chạy để build APK, nhưng nếu muốn app hoạt động đầy đủ khi
test qua Appetize (không chỉ xem UI tĩnh), Appetize cần gọi được backend qua
mạng — xem mục "App gọi backend thật" ở dưới.

## Bước 2 — Upload APK lên Appetize.io

REST API v1 của Appetize **chỉ nhận URL public tới file**, không nhận upload
file trực tiếp từ máy (`multipart/form-data`). Vì vậy có 2 cách:

### Cách A — Kéo-thả trên dashboard (khuyến nghị, không cần host APK)

1. Đăng ký/đăng nhập tại <https://appetize.io> (tài khoản của bạn — Claude
   không tự tạo tài khoản hoặc nhập thông tin đăng nhập hộ).
2. Vào **Upload App**, kéo-thả `app-debug.apk` vào đó.
3. Sau khi upload xong, dashboard hiện `publicKey` (còn gọi là `buildId`) của
   app — copy lại giá trị này.

### Cách B — Qua API, nếu APK đã có sẵn ở một URL public

Ví dụ APK đã đính kèm vào một GitHub Release. Dùng script có sẵn:

```powershell
$env:APPETIZE_API_TOKEN = "tok_..."   # lấy trong Appetize dashboard > API keys
./scripts/upload_appetize.ps1 -ApkUrl "https://github.com/<org>/<repo>/releases/download/.../app-debug.apk"
```

Script gọi `POST https://api.appetize.io/v1/apps` với header `X-API-KEY` và
body `{"platform": "android", "url": "<link>"}`, in ra `publicKey`.

**Đừng commit `APPETIZE_API_TOKEN` vào repo hay `.env`** — chỉ set tạm trong
shell session hoặc secret manager của CI.

## Bước 3 — Điền config cho trang web

```bash
cd web/public/emulator
cp config.example.js config.js
```

Sửa `config.js`:

```js
window.APPETIZE_CONFIG = {
  publicKey: "dán publicKey vào đây",
  device: "pixel7",
  osVersion: "13.0",
  scale: "75",
  orientation: "portrait",
  autoplay: false,
};
```

`config.js` đã được thêm vào `.gitignore` — mỗi người dùng public key riêng
của mình, không cần đồng bộ qua git.

## Bước 4 — Mở trang test

```bash
cd web
npm install   # nếu chưa
npm run dev
```

Mở `http://localhost:5173/emulator/`. Nếu build production (`npm run build`),
trang cũng có sẵn ở `/emulator/` vì `web/dist/` được `src/main.py` mount vào
`/`.

Trang sẽ hiện thông báo hướng dẫn nếu chưa có `publicKey`, hoặc player
Appetize nếu đã cấu hình xong.

## App gọi backend thật

`android/app/src/main/java/.../data/remote/ApiConfig.kt` trỏ `BASE_URL` tới
`http://10.0.2.2:8000/api/v1/` — chỉ đúng khi chạy trên emulator cục bộ.
Instance Appetize là máy khác hoàn toàn, không thấy `10.0.2.2` hay `localhost`
của bạn. Muốn app trên Appetize gọi được backend thật, cần:

1. Deploy backend FastAPI lên một địa chỉ public (hoặc dùng tunnel như
   `ngrok`/`cloudflared` cho môi trường thử nghiệm).
2. Build một APK riêng (build variant hoặc sửa tạm `ApiConfig.kt`) với
   `BASE_URL` trỏ tới địa chỉ public đó, rồi upload APK này lên Appetize.

Nếu chỉ cần demo UI/luồng màn hình mà chưa cần dữ liệu thật, có thể bỏ qua
bước này — app vẫn chạy được, chỉ là các màn hình gọi API sẽ lỗi kết nối.

## Guardrail — không đưa dữ liệu bệnh nhân thật vào bản demo

Link embed Appetize (`publicKey`) không phải secret tuyệt đối — ai có link đều
xem và điều khiển được app đang chạy. Theo đúng ràng buộc trong
[`CLAUDE.md`](../CLAUDE.md), bản build dùng để demo public:

- Chỉ dùng dữ liệu mock/demo (tài khoản debug `0900000000` / PIN `123456` có
  sẵn trong app khi backend chưa bật — xem [`android/README.md`](../android/README.md)).
- Không trỏ vào backend production có dữ liệu bệnh nhân thật.
- Không log OTP/token/PHI thật trong bản build này.
