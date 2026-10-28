# Quyết định xử lý các lỗi rà soát hệ thống (SEC, P, O) – bản ghi tạm

Ngày ghi: 28/10/2026. Nguồn: `docs/Dosely_Audit_Issues_2026-10-26.docx` (mục 5 Bảo mật, mục 6 Hiệu năng, mục 7 Tổ chức code và vận hành).
Bản ghi này dùng để gom sửa vào docx một lần khi file docx được đóng. Chưa triển khai mã nguồn.
Phần A: lỗi bảo mật (SEC). Phần B: lỗi hiệu năng (P). Phần C: lỗi tổ chức code và vận hành (O).

## Phần A. Lỗi bảo mật (SEC)

Quy ước cột "Nguồn quyết định":
- **Đã chốt**: bạn đã chọn trực tiếp.
- **Theo thực hành tốt**: bạn đồng ý xử lý theo hướng thực hành tốt của cộng đồng; nội dung cụ thể dưới đây là đề xuất của tôi, chưa thảo luận chi tiết.

### Bảng quyết định SEC

| Mã | Vấn đề | Quyết định | Nguồn | Ảnh hưởng UX |
|---|---|---|---|---|
| SEC-01 | Bác sĩ xem/ack/resolve alert của mọi bệnh nhân | Bỏ khỏi danh sách lỗi: chủ đích thiết kế | Đã chốt | Không |
| SEC-02 | Bác sĩ tra bệnh nhân toàn hệ thống theo số điện thoại | Bỏ khỏi danh sách lỗi: chủ đích thiết kế | Đã chốt | Không |
| SEC-03 | PIN 6 số, không khóa tài khoản | Giữ PIN 6 số (chủ đích). Chặn thử sai theo khoảng thời gian bằng Redis, khóa theo số điện thoại. Không làm API cấp lại PIN | Đã chốt | Có: màn đăng nhập web và Android cần thông báo "thử lại sau X phút" |
| SEC-04 | Giới hạn tốc độ tin `X-Forwarded-For` | Chạy uvicorn với `--proxy-headers --forwarded-allow-ips=<IP/dải mạng Caddy>`; `get_client_ip` chỉ dùng `request.client.host` | Đã chốt | Không |
| SEC-05 | Access token không kiểm lại trạng thái; logout không kiểm chủ token | Chỉ sửa logout: kiểm refresh token thuộc `current_user`. Giữ access token stateless, ghi chú giới hạn 30 phút trong tài liệu | Đã chốt | Không |
| SEC-06 | Không kiểm độ mạnh JWT secret/pepper; `APP_ENV` mặc định development | `min_length=32` cho `jwt_secret_key` và `password_pepper`; tách cờ `sql_echo` riêng, mặc định tắt. Không đổi mặc định `app_env` | Đã chốt (nhóm A, theo gợi ý) | Không |
| SEC-07 | Token WebSocket trên query string, không kiểm hết hạn | Bỏ token khỏi URL: xác thực bằng tin nhắn đầu tiên sau khi kết nối (hoặc subprotocol); đóng socket khi token hết hạn. Phải sửa client web và Android | Theo thực hành tốt | Không đổi giao diện |
| SEC-08 | Upload `/chat/voice` không giới hạn kích thước | Giới hạn kích thước (ví dụ 10 MB) và kiểm content-type âm thanh; đặt `request_body max_size` ở Caddy | Theo thực hành tốt | Không (chỉ báo lỗi khi vượt) |
| SEC-09 | SOS không rate-limit, payload không giới hạn độ dài | Giới hạn `message` ~500 ký tự, `metadata` vài KB, `resolution_note` ~1000 ký tự. Rate-limit mềm ~5 lần/phút theo bệnh nhân; vượt ngưỡng thì trả lại alert đã tạo, không báo lỗi để không chặn SOS thật. Cài trong service SOS (không dùng dependency `rate_limit_by_user` vì nó ném 429): tra alert SOS đang mở trong cửa sổ rồi trả lại. Trần `metadata` phải đủ cho evidence của agent (alert `SEVERE_SYMPTOM`) | Đã chốt | Không |
| SEC-10 | Chi phí LLM chỉ chặn theo phút | Thêm giới hạn theo ngày cho chat (`rate_limit_by_user("chat_daily", …)`) + đặt hạn mức chi tiêu hằng tháng trên dashboard OpenAI. Client web và Android hiển thị thông báo 429 thân thiện. Không đổi xử lý khi Redis lỗi | Đã chốt | Có: thông báo hết lượt trong ngày |
| SEC-11 | APK update không checksum, URL dựng từ request | Backend trả thêm `sha256` của APK; Android kiểm trước khi cài; URL tải lấy từ cấu hình HTTPS cố định, không dựng từ Host của request | Theo thực hành tốt | Không đổi giao diện |
| SEC-12 | Caddy thiếu header bảo mật, giới hạn body | Thêm HSTS, `X-Content-Type-Options: nosniff`, chống nhúng khung (`X-Frame-Options`/`frame-ancestors`), `Referrer-Policy`, `request_body max_size`. CSP thêm sau và thử kỹ vì có thể làm vỡ web | Theo thực hành tốt | Không |
| SEC-13 | CORS `allow_credentials` + methods/headers `*` | Liệt kê origin tường minh (có strip khoảng trắng), chỉ cho phép method và header cần dùng; không chấp nhận danh sách rỗng ở production. Compose và `.env` phải đặt tường minh `APP_ENV=production` (SEC-06 giữ mặc định development) | Theo thực hành tốt | Không |
| SEC-14 | Swagger/OpenAPI và `/health` công khai | Tắt `docs_url`, `redoc_url`, `openapi_url` ở production; `/health` không trả `env`. Compose và `.env` phải đặt tường minh `APP_ENV=production` (SEC-06 giữ mặc định development) | Theo thực hành tốt | Không |
| SEC-15 | Redis không mật khẩu, publish cổng ra host | Đặt `requirepass` cho Redis, cập nhật `REDIS_URL` và Celery broker; bỏ publish cổng 6379 ra host nếu không cần | Theo thực hành tốt | Không |
| SEC-16 | `COPY . .` có thể đóng gói `firebase-adminsdk.json`, dữ liệu cục bộ | Bổ sung `.dockerignore`: `firebase-adminsdk.json`, `downloads/`, `android/`, `tests/`; chỉ đưa secret vào qua volume/biến môi trường | Theo thực hành tốt | Không |
| SEC-17 | PHI/token trong log | Bỏ `evidence` triệu chứng và số điện thoại khỏi log (hoặc che bớt), tắt SQL echo (gắn với SEC-06), thay `print` bằng logger | Theo thực hành tốt | Không |
| SEC-18 | `X-Request-ID` do client điều khiển | Kiểm định dạng và độ dài (UUID hợp lệ), sai thì tự sinh mới | Theo thực hành tốt | Không |
| SEC-19 | Refresh token không `jti`, không phát hiện tái sử dụng | Thêm `jti`; xoay vòng refresh token mỗi lần dùng; khi token đã thu hồi bị dùng lại thì thu hồi cả phiên; khóa dòng khi refresh để tránh đua. Có cửa sổ dung sai khoảng 30 giây cho retry khi mất phản hồi (web single-flight, Android authenticator) để không đăng xuất oan | Theo thực hành tốt | Không (chỉ buộc đăng nhập lại khi phát hiện bất thường) |
| SEC-20 | FCM token bị gán lại sang tài khoản khác | Xóa FCM token của thiết bị khi logout; giữ upsert khi đăng nhập trên thiết bị mới. API logout nhận thêm FCM token (hoặc device id) của thiết bị, client web và Android gửi kèm; phối hợp với kiểm tra chủ token của SEC-05 | Theo thực hành tốt | Không |
| SEC-21 | Telegram `link_code` không hết hạn, không giới hạn thử | Bỏ, không sửa | Đã chốt | Không |
| SEC-22 | Dependency dùng `>=`, không lockfile | Ghim phiên bản (lockfile, ví dụ `pip-compile`), tách `requirements-dev.txt` khỏi image production | Theo thực hành tốt | Không |
| SEC-23 | Lỗi nội bộ lọt vào câu trả lời | Thông điệp chung cho lỗi backend và voice trong `backend_client.py` và luồng voice; chi tiết chỉ ghi log. Giữ nguyên lỗi 422 của FastAPI | Đã chốt | Có: nội dung báo lỗi chat đổi sang câu chung |
| SEC-24 | PIN demo công khai, LIKE không escape | Bỏ PIN demo khỏi README và tài liệu; escape `%` và `_` trong tìm kiếm `ilike` | Theo thực hành tốt | Không |

### Cần chỉnh khi cập nhật docx (SEC)

1. Mục 5 (Bảo mật): chuyển SEC-01 và SEC-02 sang nhóm "chủ đích thiết kế", bỏ SEC-21 khỏi danh sách lỗi. Số vấn đề mục này từ 24 xuống 21.
2. Bảng thống kê và mục "Tổng quan": High từ 58 xuống 56; tổng từ 236 xuống 233. Cập nhật các con số theo cách phân loại mức của từng mục còn lại.
3. "Ưu tiên cao nhất": bỏ SEC-01 và SEC-02, chỉ giữ SEC-03.
4. Mail gửi thầy Trung: bỏ ý "phân quyền bác sĩ chưa chặt" khỏi nhận định bảo mật, đổi các con số 236, 58, 24.

## Phần B. Lỗi hiệu năng (P)

Toàn bộ 14 mã dưới đây không đổi flow người dùng khi hệ thống chạy bình thường. Tất cả theo khuyến nghị của tôi (đã được bạn đồng ý), chưa thảo luận chi tiết từng mục. P-11 đã chốt (bộ đếm nguyên tử + fail-open). P-12 đã chốt bỏ qua. Toàn bộ mã nhóm P đã có quyết định.

### Bảng quyết định P

| Mã | Vấn đề | Quyết định | Nguồn | Ảnh hưởng UX |
|---|---|---|---|---|
| P-01 | 8 task Celery tự tạo engine NullPool mỗi lần chạy | Gom về một helper `task_session()`, giữ `NullPool` (đánh đổi có chủ đích vì mỗi `asyncio.run` có event loop riêng) | Theo khuyến nghị | Không |
| P-02 | `scan_due_doses` tải toàn bộ liều quá hạn, N+1 theo nhóm | Thêm cận dưới thời gian cho truy vấn; kiểm tra idempotency theo lô bằng một truy vấn `IN`. Cận dưới phải ≥ `missed_dose_overdue_minutes` (60 phút) để không bỏ sót liều quá hạn | Theo khuyến nghị | Không |
| P-03 | bcrypt đồng bộ trên event loop, trong transaction | Chạy bcrypt bằng `asyncio.to_thread`; băm/kiểm xong rồi mới mở transaction (đăng nhập, đổi PIN, tạo bệnh nhân, đơn thuốc, admin) | Theo khuyến nghị | Không |
| P-04 | WebSocket dashboard giữ DB session suốt kết nối | Mở session ngắn cho từng frame thay vì giữ suốt vòng đời kết nối | Theo khuyến nghị | Không |
| P-05 | Engine chính chưa cấu hình pool | Thêm `pool_pre_ping=True`, `pool_recycle`, kích thước pool phù hợp với Supabase pooler | Theo khuyến nghị | Không |
| P-06 | Danh sách bệnh nhân dashboard dùng subquery tương quan trong ORDER BY | Tính trước số liệu cảnh báo/liều bằng join + `GROUP BY` rồi mới sắp xếp; kết quả hiển thị giữ nguyên | Theo khuyến nghị | Không |
| P-07 | Xóa cache bằng `SCAN` toàn keyspace Redis | Dùng cache key theo nhóm (set theo prefix) hoặc phiên bản hóa key thay cho `SCAN` | Theo khuyến nghị | Không |
| P-08 | FCM gọi đồng bộ; báo cáo caregiver N+1 và kéo toàn bộ liều về Python | Gọi FCM qua `to_thread`; đếm trạng thái liều bằng một truy vấn `GROUP BY` | Theo khuyến nghị | Không |
| P-09 | RAG nạp lười ở request đầu, `fold()` lặp mỗi truy vấn | Warm-up lúc khởi động; tính sẵn bảng tên đã chuẩn hóa một lần. Warm-up fail-soft (thiếu index chỉ ghi log cảnh báo, không làm app hoặc test khởi động lỗi) và chỉ warm-up một instance RAG dùng chung | Theo khuyến nghị | Không (request đầu nhanh hơn) |
| P-10 | `httpx.AsyncClient` mới cho mỗi tool call của agent | Dùng một client chung, tái dùng kết nối, đóng khi tắt app | Theo khuyến nghị | Không |
| P-11 | Rate limit INCR+EXPIRE không nguyên tử; Redis lỗi thì 500 | Làm bộ đếm nguyên tử (gộp INCR và đặt hạn, ví dụ pipeline hoặc SET NX EX rồi INCR). Redis lỗi thì cho qua (fail-open) và ghi log cảnh báo, không trả 500 | Đã chốt | Không (chỉ khác khi Redis sự cố: app vẫn dùng được) |
| P-12 | Không có Beat job gia hạn lịch sau 14 ngày | Bỏ qua, không sửa | Đã chốt | Không |
| P-13 | Celery không time limit, không tách queue | Đặt `task_time_limit` và `soft_time_limit`; tách queue riêng cho review LLM và nhắc thuốc. Job review có ngưỡng riêng lớn hơn (trường hợp xấu nhất ~100 phút). Sửa `docker-compose.yml` để worker chạy với `-Q` cho các queue mới, nếu không task ở queue mới không được nhận | Theo khuyến nghị | Không |
| P-14 | Tìm kiếm `ilike '%term%'` phụ thuộc index trigram | Không sửa code; kiểm tra `pg_trgm` và index tồn tại sau khi chạy migration, ghi chú trong tài liệu triển khai | Theo khuyến nghị | Không |

### Cần chỉnh khi cập nhật docx (P)

1. Mục 6 (Hiệu năng): ghi quyết định xử lý cho từng mã. P-12 đánh dấu "bỏ qua".
2. P-01 ghi rõ đây là đánh đổi có chủ đích (NullPool), chỗ cần sửa là code trùng lặp. P-14 là rủi ro phụ thuộc cấu hình, không phải lỗi mặc định.

## Phần C. Lỗi tổ chức code và vận hành (O)

Phần này gồm 20 mã, tất cả theo khuyến nghị của tôi (đã được bạn đồng ý). 17 mã không đổi flow người dùng; ba mã O-01, O-02, O-04 đã được thảo luận riêng vì cải thiện độ tin cậy và độ chính xác của thông báo.

### Bảng quyết định O

| Mã | Vấn đề | Quyết định | Nguồn | Ảnh hưởng UX |
|---|---|---|---|---|
| O-01 | Enqueue Celery sau commit không có outbox; delivery `QUEUED` mồ côi không bao giờ gửi lại | Khi quét, delivery còn `QUEUED` quá N phút (ví dụ 2 phút) thì enqueue lại; việc gửi đã có kiểm trạng thái nên không gửi trùng. Không làm outbox đầy đủ. Delivery `SENDING` quá hạn (worker chết giữa chừng) cũng được coi như `QUEUED` để gửi lại | Đã chốt | Có lợi: nhắc thuốc ít bị mất khi sự cố, flow không đổi |
| O-02 | Gửi thông báo không claim nguyên tử; lỗi FCM tạm thời thành `FAILED` vĩnh viễn | Claim nguyên tử (`UPDATE … SET status='SENDING' WHERE status IN ('QUEUED','RETRYING') RETURNING`) trước khi gửi; phân biệt lỗi tạm thời (mạng, 5xx) với lỗi vĩnh viễn (token chết), lỗi tạm thời thì retry tối đa 3 lần như nhánh Telegram. Trạng thái `SENDING` mới nằm trong `VARCHAR(20)` và không có CHECK trên status nên không cần migration | Đã chốt | Có lợi: ít push trùng, ít nhắc thuốc bị mất |
| O-04 | Nhắc thuốc và báo cáo dùng giờ Việt Nam cố định, `ZoneInfo` lỗi thì in giờ UTC | Truyền `PatientProfile.timezone` vào `format_notification_text`; lỗi thì fallback giờ Việt Nam và ghi log cảnh báo; đảm bảo `tzdata` trong `requirements.txt`. Job crontab theo từng múi giờ: bỏ qua, ghi là giới hạn đã biết | Đã chốt | Giờ trong thông báo khớp múi giờ bệnh nhân (người dùng ở Việt Nam không thấy khác) |
| O-03 | Hai lần quét chồng lấn làm vi phạm UNIQUE, rollback cả lô | Dùng `INSERT … ON CONFLICT DO NOTHING` (ưu tiên hơn bắt `IntegrityError` vì Postgres hủy cả transaction khi lỗi và O-05 không dùng savepoint) | Theo khuyến nghị | Không |
| O-05 | Quản lý transaction không nhất quán | Bỏ qua (refactor rộng, rủi ro cao); chỉ ghi quy ước vào tài liệu | Theo khuyến nghị | Không |
| O-06 | Logic nghiệp vụ nằm trong `agents/tasks.py` | Chuyển vào service/repository, `tasks.py` chỉ gọi | Theo khuyến nghị | Không |
| O-07 | Phụ thuộc vòng `adherence` và `agents` | Bỏ qua (đang chạy ổn) | Theo khuyến nghị | Không |
| O-08 | Thư mục chồng lấn `src/agents`, `src/modules/agents`, `src/modules/planning` | Làm: gộp theo ranh giới rõ (graph/node/tool của agent tách khỏi phần backend module: router, service, repository, tasks). Phạm vi Project 3 bao gồm cả `src/agents/` | Đã chốt | Không |
| O-09 | Logic lặp: bộ lọc truy cập, công thức phân trang | Làm phần phân trang bằng helper chung; bỏ phần `_access_filter` | Theo khuyến nghị | Không |
| O-10 | File quá lớn, `agents/service.py` 1061 dòng | Tách thành 3 file, chỉ di chuyển code; làm sau cùng nếu còn thời gian | Theo khuyến nghị | Không |
| O-11 | 720 lỗi `ruff`, có lỗi thật | `ruff --fix`; sửa `get_settings` chưa import (`agents/router.py:58`) và khóa dict lặp (`graph.py:130`); cho CI lint chặn | Theo khuyến nghị | Không |
| O-12 | Test không chạy được từ checkout sạch, dùng DB thật | Thêm cấu hình pytest, `.env.test`, DB test riêng, tránh ghi vào DB thật | Theo khuyến nghị | Không |
| O-13 | `scripts/` và `tests/` tổ chức lộn xộn | Chia thư mục con cho scripts, bổ sung `__init__.py` | Theo khuyến nghị | Không |
| O-14 | `requirements.txt` trộn dev/prod, `pyproject.toml` lỗi thời | Tách `requirements-dev.txt`, cập nhật `pyproject.toml`; gộp với SEC-22 | Theo khuyến nghị | Không |
| O-15 | Migration trùng số, ID lệch tên file | Bỏ qua (đổi revision ID rủi ro cao); chỉ ghi tài liệu | Theo khuyến nghị | Không |
| O-16 | `log_level` không áp dụng, dùng `print` | Cấu hình `logging.basicConfig` theo `log_level`, bỏ `print`, gắn request id vào log | Theo khuyến nghị | Không |
| O-17 | Biên dịch LangGraph lúc import | Bỏ qua | Theo khuyến nghị | Không |
| O-18 | Tên không đồng nhất (ADHE REMIND API, adhe_remind_tasks, ai20k-agent) | Đổi toàn bộ sang Dosely, cập nhật `tests/test_api/test_core.py:18` và `.env.example` | Theo khuyến nghị | Không |
| O-19 | `except Exception` rộng che lỗi thật | Thu hẹp loại exception, log với `exc_info` | Theo khuyến nghị | Không |
| O-20 | Một worker uvicorn, image chứa `android/` và `tests/`, không có bước migration | Thêm `--workers`, bổ sung `.dockerignore`, thêm bước `alembic upgrade head` trong compose hoặc entrypoint; gộp với SEC-16 | Theo khuyến nghị | Không |

Toàn bộ 20 mã nhóm O đã có quyết định.

### Cần chỉnh khi cập nhật docx (O)

1. Mục 7 (Tổ chức code và vận hành): ghi quyết định xử lý cho từng mã.
2. O-05, O-07, O-15, O-17 ghi rõ là bỏ qua có chủ đích; O-14 và O-20 ghi liên kết với SEC-22 và SEC-16.

## Nhật ký triển khai

Ghi lại các quyết định phát sinh trong lúc triển khai (tự quyết khi không quá quan trọng; mục quan trọng ghi "chờ chỉ thị").

### Mảng 1: hạ tầng test và lint (O-12, O-11) — đã push

- Phát hiện thêm: backend không khởi động được do `requirements.txt` không ghim phiên bản, SQLAlchemy 2.1 không còn kéo `greenlet`. Đã sửa bằng `sqlalchemy[asyncio]`. Ghim phiên bản đầy đủ vẫn để ở SEC-22/O-14.
- Phát hiện thêm: `docs/database_v1_init.sql` không chạy được trên DB trống (khóa ngoại `adherence_reviews` trỏ tới `notification_deliveries` khai báo trước khi bảng được tạo). Đã sửa thứ tự.
- DB test riêng: Postgres cổng 5433, Redis cổng 6380 (`docker-compose.test.yml`), `.env.test` chỉ chứa giá trị giả. `tests/db_guard.py` chặn chạy test nếu `DATABASE_URL` không phải loopback với tên DB kết thúc `_test`.
- CI: job lint `ruff` chuyển sang chặn. Job `backend-tests` vẫn để `continue-on-error` vì còn 16 test chatbot fail đã biết (chờ quyết định nhóm CHAT).
- `ruff.toml`: bỏ qua N818 (`AppException`) và UP042 (các lớp `(str, Enum)`) theo từng file, có chú thích lý do.
- Phát hiện thêm và đã sửa: refresh token trùng khi cấp hai lần trong cùng một giây (gây `UniqueViolation`). Đã thêm `jti` ngẫu nhiên vào access và refresh token. Phần xoay vòng và phát hiện dùng lại vẫn để ở SEC-19.
- `tests/test_api/test_patient_app.py` (test cho app demo trong bộ nhớ đã bị gỡ) được viết lại thành 5 test chạy trên DB thật; 4 test cũ bị bỏ vì `test_alerts.py` đã phủ cùng hành vi.
- Các test tổng hợp tuân thủ được sửa để không phụ thuộc giờ trong ngày (trước đây fail sau nửa đêm giờ Việt Nam).
- Kết quả: 735 pass, 16 fail (đều thuộc chatbot, giữ nguyên chủ ý), `ruff` 0 lỗi.

### Mảng 2: cấu trúc (O-18, O-13, O-08, O-10, O-06, O-09) — đã push

- Tên Celery app đổi thành `dosely_tasks`; giữ nguyên toàn bộ tên task tường minh (`agents.*`, `adherence_review.scan`) để task đang xếp hàng vẫn chạy được.
- `scripts/` chia thành `scripts/rag/` và `scripts/db/`. Giữ nguyên `scripts/_pyrun.*` và `scripts/doc_audit_hook.py` vì hook trong `.claude/settings.json` trỏ tới.
- `src/agents/` đổi thành `src/chatbot/`; `src/modules/planning/core/` chuyển vào `src/chatbot/clients/`. `tests/test_agents/` đổi thành `tests/test_chatbot/`; test của router backend (`test_schedule_self_routes`) chuyển sang `tests/test_services/`.
- `src/modules/agents/service.py` tách thành `scheduling_service.py`, `missed_dose_scan_service.py`, `chat_service.py`, không giữ shim tương thích.
- Logic báo cáo người thân và tổng hợp tác dụng phụ chuyển sang `caregiver_report_service.py` và `adverse_event_summary_service.py` trong module adherence; ranh giới transaction giữ như cũ. `_execute_send_notification` để nguyên cho Mảng 5.
- `page_count` ném `ValueError` khi `size < 1`; mọi endpoint đã khai báo `size` với `ge=1` nên không thể gây lỗi 500.
- Kết quả: 752 pass, 16 fail (chatbot), `ruff` 0 lỗi, 8 task Celery đăng ký đầy đủ như trước.

### Mảng 3: cấu hình và hạ tầng bảo mật (SEC-06, 08, 11, 12, 13, 14, 15, 16, 17, 18, 22, 24, O-14, O-16, O-20) — đã push

Quyết định tự đưa ra:
- `src/main.py` chuyển sang hàm `create_app()`; vẫn giữ `src.main:app` cho uvicorn và Dockerfile.
- Voice upload chấp nhận mọi `audio/*` (Android gửi `audio/mp4`, web gửi `audio/webm`), giới hạn mặc định 10 MB; Caddy giới hạn body 12 MB.
- Escape LIKE áp dụng thêm cho tìm kiếm ở admin và patients (cùng lỗi), dùng helper `src/common/search.py`.
- `android_download_base_url` mặc định `https://dosely.duckdns.org` (domain của Caddyfile) để bản triển khai hiện tại không đổi. `sha256` là `null` khi file APK không tồn tại.
- Android chỉ mở link APK bằng trình duyệt nên chưa kiểm hash trong app; đã mang trường `sha256` và để TODO.
- Celery worker lấy mức log từ `LOG_LEVEL`, không còn theo `--loglevel`.
- Hoãn: CSP (SEC-12), `--proxy-headers` (làm ở SEC-04, Mảng 4).
- Kiểm tra: `caddy validate` đạt, `docker compose config` đạt, image build được, `pip freeze` khớp bản ghim. Test Android chưa chạy được vì Gradle 8.7 cần JDK 17 và cache offline thiếu; file test Kotlin đã viết.
- Kết quả: 810 pass, 16 fail (chatbot), `ruff` 0 lỗi.

Chờ chỉ thị / bạn cần làm khi triển khai:
1. Thêm `REDIS_PASSWORD` (ký tự an toàn cho URL) vào `.env` triển khai; thiếu thì compose từ chối khởi động. `JWT_SECRET_KEY` và `PASSWORD_PEPPER` trong `.env` hiện tại đã đủ ≥32 ký tự.
2. Xác nhận `ANDROID_DOWNLOAD_BASE_URL` và đặt `CORS_ORIGINS` rõ ràng ở production (mặc định trong code vẫn là localhost).
3. `UVICORN_WORKERS` mặc định 2, chưa đo RAM trên VPS 3,8 GB; nếu thiếu RAM đặt 1.
4. Service `migrate` chỉ chạy `alembic upgrade head`, giả định DB đã có schema gốc từ `docs/database_v1_init.sql`; DB hoàn toàn mới chưa tự dựng được.
5. Redis không còn mở cổng ra máy; chạy uvicorn ngoài compose cần Redis riêng.
6. HSTS bật cho domain duckdns (kèm `includeSubDomains`): trình duyệt sẽ từ chối HTTP trong một năm.

Ghi chú khác (ngoài phạm vi, chưa sửa): `.git/hooks/pre-push` và `post-merge` gọi `scripts/log_antigravity.py`, `scripts/submit_log.py` đã bị xóa từ trước, nên mỗi lần push in lỗi nhưng không chặn push.
