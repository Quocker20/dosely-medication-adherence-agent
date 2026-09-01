# Weekly Journal — Team P-216 (RemindRx / VMEC-04)

> Ghi lại mỗi tuần: học được gì, khó khăn gì, quyết định gì, kế hoạch tiếp.
> Dự án bắt đầu 25/07/2026 (template), code RemindRx đầu tiên 07/08/2026.

---

## Week 2 (03/08 - 09/08): Setup & nền móng

### Mục tiêu tuần này
- [x] Dựng hạ tầng backend chuẩn (FastAPI + Postgres + Redis + Celery + Docker)
- [x] Màn hình doctor portal đầu tiên
- [x] Sửa AI-log hook chạy được trên Windows

### Đã hoàn thành
- Core infrastructure: security, database, Redis, Celery, env template sạch (Quocker20).
- Doctor portal đầu tiên: dashboard, e-prescription, alerts (Son).
- Phân tích scope agent nhắc thuốc làm nền cho guardrail sau này (Kizo-pito).

### Khó khăn & Giải pháp
| Khó khăn | Giải pháp | Kết quả |
|----------|-----------|---------|
| AI-log hook bị BOM phá shebang trên Windows, stub Python làm kẹt submit | Fix encoding + thay stub (Kizo-pito) | Hook chạy được mọi máy |

### Bài học
- Đầu tư hạ tầng + hook logging ngay tuần đầu giúp mọi commit sau có truy vết AI theo quy định BTC.

### Kế hoạch tuần sau
- [x] Dựng các vertical slice: auth → admin → patient → prescription → adherence

---

## Week 3 (10/08 - 16/08): Vertical slices

### Mục tiêu tuần này
- [x] Auth slice hoàn chỉnh (PIN, refresh token)
- [x] Backend slices 3–7 (patient, routine, prescription, adherence)
- [x] Android client gốc + agent chat/voice end-to-end

### Đã hoàn thành
- Auth + admin module với row-level locking chống race condition (Quocker20/AnhVQ).
- Slices 3–7: patient roster, medication catalog, routines, prescription CRUD, adherence logging + safety alerts (Quocker20).
- Android client Kotlin + Compose, unit tests, mapper layer (Son).
- Agent: tool-calling với LLM, `compute_schedule`, voice chat end-to-end, missed-dose scan + guardrail frequency (Kizo-pito).
- Gate 2 deliverables nộp đúng hạn (Đat.).

### Khó khăn & Giải pháp
| Khó khăn | Giải pháp | Kết quả |
|----------|-----------|---------|
| Race condition khi tạo/cập nhật doctor | Row-level locking + harden duplicate-constraint detection | Không còn dirty data |
| AsyncSession autobegin conflict khi tạo caregiver | Đưa DB operation về một transaction ở service layer | Sửa ổn định |
| Test suite không chạy được với DB thật | Viết fixture kết nối DB thật (Quocker20) | Suite tin cậy hơn |

### Bài học
- Vertical slice mỗi PR một tính năng end-to-end giúp nhóm 5-6 người làm song song mà ít đụng chạm.
- Transaction phải nằm ở service layer, không để router tự quản.

### Kế hoạch tuần sau
- [x] RAG tra cứu thuốc, planning agent v1, push notification FCM

---

## Week 4 (17/08 - 23/08): RAG, Planning Agent v1, FCM

### Mục tiêu tuần này
- [x] Drug formulary RAG pipeline có nguồn
- [x] Planning Agent v1.0
- [x] Pipeline push notification FCM từ backend tới Android

### Đã hoàn thành
- RAG pipeline an toàn cho formulary thuốc, tích hợp vào chatbot (Kizo-pito).
- Planning Agent v1.0 (Son).
- FCM đầy đủ: notification grouping, user_devices, Celery Beat scan, Android foreground/background notification, xử lý review (runtime permission, snooze guardrail) (Đat.).
- Web bệnh nhân có chatbot + dashboard filter adherence (Son).
- CI chuyển sang self-hosted runner của BTC.

### Khó khăn & Giải pháp
| Khó khăn | Giải pháp | Kết quả |
|----------|-----------|---------|
| Missed-dose streak tính cả dose tương lai | Loại future doses khỏi lookup | Số liệu đúng |

### Bài học
- RAG phải tách bạch "tra cứu có nguồn" khỏi "tư vấn" — đúng ràng buộc không dùng RAG để chẩn đoán/liều.

### Kế hoạch tuần sau
- [x] Deploy production, adherence review, offline sync, release Android đầu tiên

---

## Week 5 (24/08 - 30/08): Production thật

### Mục tiêu tuần này
- [x] Deploy hệ thống ra internet (web + API + APK tải được)
- [x] Adherence graded-severity review hoàn chỉnh
- [x] Android offline-first + release có ký số
- [x] Rate limiting + caching + onboarding gates

### Đã hoàn thành
- Deploy: Caddy + DuckDNS, web build vào Docker, Vercel, versioned APK link (Son).
- Adherence review 7 stage: foundation → LLM remedy classification → nightly job + action routing → severity-weighted roster → doctor portal UI (Quocker20).
- Android v1.0 → v1.3.0: offline outbox sync + Room cache, build ký số đầu tiên với keystore gitignored (Son).
- Bảo mật & hiệu năng: Redis rate limit (login/chat), read-through cache, adherence % đúng (Son/Quocker20).
- Realtime fix: dose action trước 20 phút, dose lock re-scan 30s (Quocker20).
- Chatbot: hybrid medication context, giải thích thuốc/next dose, LLM-first routing, output guard chặn câu trả lời không nguồn (Kizo-pito).

### Khó khăn & Giải pháp
| Khó khăn | Giải pháp | Kết quả |
|----------|-----------|---------|
| Hai nhánh lớn (chat-memory, adherence-review) đụng DB cùng lúc → nhiều migration heads | Gom heads, chia DDL 0020 thành từng statement, viết docs cho 0025 | Tree về một head |
| Cloudflare cache cũ APK khiến user tải nhầm version | Version link tải APK (Son) | Luôn tải đúng bản mới |
| Nightly adherence job crash production (sửa đầu Week 36) | Fix crash + idempotent-replay check | Job đêm ổn định |

### Bài học
- Merge migration heads sớm và thường — hai feature lớn cùng đụng DB là sự kiện chắc chắn xảy ra, không phải rủi ro.
- Keystore phải gitignored ngay từ lần build ký đầu tiên.

### Kế hoạch tuần sau
- [x] Cứng hóa guardrail chat + planning agent 2.0

---

## Week 6 (31/08 - 06/09): Guardrail & Planning Agent 2.0

### Mục tiêu tuần này
- [x] Chốt kiến trúc Planning Agent: deterministic core, bỏ LLM khỏi đường sinh lịch
- [x] Cứng hóa guardrail chat: scope, abuse, khẩn cấp, câu trả lời không có nguồn
- [x] API lịch sử hội thoại chat (list + detail)
- [x] Android v1.4/v1.5 + PDF export đơn thuốc
- [x] Đưa `feature/planning-agent` vào PR/review

### Đã hoàn thành
- **Planning Agent 2.0 (Son):** pipeline 3 phase (snapshot → deterministic draft → locked commit + audit) qua Celery, trả 202 + `agent_run_id`. Core `expand_schedule()` thuần rule: 4 slot neo bữa ăn, meal_relation offset, horizon 14 ngày, validators bằng code. Reschedule chỉ dời GIỜ — đúng HITL.
- **Quyết định kiến trúc: bỏ LLM notification grouping** — validator yêu cầu khớp timestamp chính xác nên LLM vô dụng nhưng tốn ~15s timeout. Giờ `candidate_source = "deterministic"`, flag `planning_grouping_enabled=false` giữ lại.
- **Guardrail chat (Kizo-pito):** chặn abusive trước routing, redirect khẩn cấp sang SOS, chặn out-of-scope ngữ nghĩa trước planner, chặn câu trả lời y tế không nguồn ở output guard; adverse event bắt buộc xác nhận triệu chứng.
- **Fix bug (Son):** chat history 500; write step rơi trong multi-tool plan → guard `write_not_composable`; conflict reschedule miss window vắt nửa đêm → so datetime theo timezone bệnh nhân; verdict "Có"/"CÓ" → normalize bỏ dấu Unicode.
- **API lịch sử hội thoại (Son):** list (cache Redis) + detail có ownership check, cursor pagination, schemas camelCase/snake_case.
- **Khác:** PDF export đơn thuốc + dark-mode toàn portal (Quocker20); Android v1.4.0 (chat history) → v1.5.0 (launcher icon, update sideload) (Son).

### Khó khăn & Giải pháp
| Khó khăn | Giải pháp | Kết quả |
|----------|-----------|---------|
| LLM grouping tốn 15s timeout mà output vẫn bị validator từ chối | Cắt LLM khỏi grouping, 100% rule-based | Nhanh hơn ~15s, luôn pass validator, dễ test |
| Conflict check so time-of-day → miss ca vắt nửa đêm | So datetime đầy đủ theo timezone bệnh nhân | Detect đúng mọi window |
| Write step bị âm thầm rơi trong multi-tool plan | Guard chặn compose ngay từ `plan_guard` | Write step luôn thực thi |
| Verdict tiếng Việt có dấu không khớp keyword check | Normalize bỏ dấu Unicode | Safety guard đọc được verdict |

### Bài học
- Đừng để LLM làm phần mà validator yêu cầu độ chính xác tuyệt đối — deterministic để code, LLM chỉ ở lớp hiểu ý người dùng.
- Route tĩnh phải khai báo trước route động trong FastAPI.
- Thao tác có hệ lụy (đổi lịch, ghi nhận tác dụng phụ) cần bước xác nhận tường minh — thống nhất cả web lẫn chat agent.
- Tiếng Việt có dấu là bẫy khi so khớp verdict LLM — luôn normalize trước.

### Kế hoạch tuần sau
- [x] Tạo PR cho `feature/planning-agent`, bổ sung test API conversations trong `tests/test_api/`
- [x] Test E2E: doctor approve prescription → autoschedule → patient reschedule qua agent
- [x] Chuẩn bị demo Planning Agent cho buổi review nhóm

---

<!-- Tiếp tục copy block trên cho các tuần sau -->
