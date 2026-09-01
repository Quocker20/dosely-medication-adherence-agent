# Worklog — Team P-216 (RemindRx / VMEC-04)

> Ghi lại toàn bộ công việc của dự án từ ngày bắt đầu. Tổ chức theo tuần (326 commits, 25/07 → 01/09/2026).
> Thành viên: Son, Kizo-pito (MinhDB), Quocker20, AnhVQ, Binh Minh Dao, Đat., haxuanson (merge/review).

---

## Week 30–31 (20/07 – 02/08): Khởi động

| Member | Task | Status | Output | Time |
|--------|------|--------|--------|------|
| phoenix-mentor[bot] | Initial commit — boilerplate template AI20K | ✅ Done | Commit `2a22112` (25/07) | - |
| Đat. | First commit / sync bộ log AI interaction | ✅ Done | Scripts thu log AI qua git hooks | 1h |

**Tổng kết:** Repo template được tạo, chưa có code RemindRx thật.

---

## Week 32 (03/08 – 09/08): Setup nền tảng + màn hình đầu tiên

| Member | Task | Status | Output | Time |
|--------|------|--------|--------|------|
| Son | Doctor portal đầu tiên: dashboard, e-prescription, alerts | ✅ Done | Commit `c5275a0` (07/08) — code RemindRx đầu tiên của dự án | 3h |
| Kizo-pito | Sửa AI-log hook trên Windows (BOM phá shebang), phân tích scope agent nhắc thuốc | ✅ Done | Hooks hoạt động trên Windows; tài liệu scope agent | 2h |
| Quocker20 | Setup hạ tầng: docker-compose, .env.example, pyproject, core infrastructure (security, DB, Redis, Celery) | ✅ Done | Commits 08–09/08, PR #1 | 6h |

**Tổng kết:** Hạ tầng backend chuẩn (FastAPI + Postgres + Redis + Celery) và màn hình doctor portal đầu tiên chạy được.

---

## Week 33 (10/08 – 16/08): Vertical slices — dựng đủ luồng thô

| Member | Task | Status | Output | Time |
|--------|------|--------|--------|------|
| Quocker20 | Auth slice: login, đổi PIN, refresh token, logout; transaction gọn trong service layer | ✅ Done | PR #2 (11/08) | 8h |
| Quocker20 | Admin module: quản lý doctor + audit log, xử lý race condition bằng row-level locking | ✅ Done | PR #2/#8 kèm theo, AnhVQ đồng triển khai | 6h |
| Quocker20 | Backend slices 3–7: patient roster + medication catalog, routines + caregiver links, prescription CRUD (atomic find-or-create), adherence logging + safety alerts | ✅ Done | PRs #8–#15 (12–13/08) | 12h |
| Quocker20 | Doctor portal read models + live event feed; sửa test suite chạy được với DB thật | ✅ Done | 14/08 | 4h |
| Son | Android client gốc: Kotlin + Jetpack Compose, MVVM | ✅ Done | Commit 11/08, PR #4 | 8h |
| Son | Android: đưa UI vào `ui/feature/`, thêm unit tests, mapper layer, màn hình adherence + caregiver | ✅ Done | 13–14/08 | 8h |
| Son | API dose snapshots + schema patient/agent; test API (chat auth, routines, schedule planner) | ✅ Done | 14/08 | 4h |
| Kizo-pito | Agent: wire tool-calling vào LLM, `compute_schedule`, API contract agent tools (`record_dose_action`, SOS) + voice UI end-to-end | ✅ Done | PR #14 (13/08) | 8h |
| Kizo-pito | Agent: missed-dose scan, guardrail frequency, tra cứu thuốc thật; loại dose tương lai khỏi streak | ✅ Done | 14/08 | 3h |
| AnhVQ / Binh Minh Dao / haxuanson | Review & merge PR #1–#23 | ✅ Done | Develop/main sync liên tục | 2h |
| Đat. | Gate 2 deliverables: README + eval evidence | ✅ Done | 16/08 | 2h |

**Tổng kết:** Tuần vàng của vertical slices — từ auth → admin → patient/prescription → adherence → agent chat/voice, cả 3 platform (API, web, Android) đều có luồng thô chạy được.

---

## Week 34 (17/08 – 23/08): RAG, planning agent v1, push notification

| Member | Task | Status | Output | Time |
|--------|------|--------|--------|------|
| Kizo-pito | Drug formulary RAG pipeline (an toàn, có nguồn) | ✅ Done | 17/08 | 6h |
| Kizo-pito | Tích hợp RAG vào chatbot, giữ nguyên phân loại an toàn thuốc | ✅ Done | 24/08, PR #35 | 3h |
| Son | Web bệnh nhân: chatbot + dashboard adherence filter | ✅ Done | 18/08, PRs #24/#25 | 5h |
| Son | Planning Agent v1.0 | ✅ Done | 21/08, PR #28 | 6h |
| Son | Web: refactor cấu trúc src (pages/hooks/utils), auth flow | ✅ Done | 22–23/08 | 3h |
| Đat. | Push notification: notification grouping + dose reminder models, user_devices (FCM token), Celery Beat scan, FCM trên Android | ✅ Done | 23/08, PR #33 + fix theo review (runtime permission, snooze guardrail) | 10h |
| Son | CI: chuyển sang BTC self-hosted runner | ✅ Done | 23/08 | 1h |

**Tổng kết:** Ba mảng lớn cùng tiến: RAG tra cứu thuốc, planning agent v1, và pipeline đẩy thông báo FCM hoàn chỉnh từ backend tới Android.

---

## Week 35 (24/08 – 30/08): Deploy, adherence review, offline sync, release đầu tiên

| Member | Task | Status | Output | Time |
|--------|------|--------|--------|------|
| Son | Deploy production: Caddy + DuckDNS, web build vào Docker image, Vercel, DNS, versioned APK download link | ✅ Done | 25–29/08 | 6h |
| Son | Planning Agent auto-trigger khi doctor duyệt đơn / đổi routine | ✅ Done | 25/08 | 2h |
| Son | Security: rate limit login + chat bằng Redis; cá nhân hóa lời chào + tra hồ sơ bệnh nhân; `GET /doctors/me`, gom helper client-IP | ✅ Done | 28/08, PRs #52–#54 | 4h |
| Son | Web: landing page, patient-detail page cho doctor, tab routine/adherence, realtime events scope theo caller | ✅ Done | 28/08 | 5h |
| Son | Android: offline outbox sync + Room cache; release v1.0.0 build 2 → v1.1.0 → v1.2.0 (durable chat memory) → v1.3.0 (build ký số đầu tiên, keystore gitignored) | ✅ Done | 28–30/08 | 8h |
| Son | DB: gom migration heads (chat-memory + adherence-review), fix DDL 0020/0027 | ✅ Done | 29/08 | 2h |
| Son | CI: build web + chạy android test (VPS, tune tài nguyên), mark gradlew executable | ✅ Done | 29/08 | 2h |
| Kizo-pito | Chatbot: hybrid patient medication context, giải thích thuốc + next dose, chatbot LLM-first routing, chặn câu trả lời không có nguồn ở output guard | ✅ Done | 25–29/08 | 8h |
| Kizo-pito | RAG: resolve drug brand + mọi hoạt chất trong thuốc phối hợp | ✅ Done | 31/08 (làm từ 30/08) | 2h |
| Quocker20 | Adherence graded-severity review Stage 1–7: foundation → LLM remedy classification → nightly job + action routing → severity-weighted roster → portal UI + critical dose flag | ✅ Done | 29/08, PR #69 | 14h |
| Quocker20 | Fix realtime: dose action ghi nhận trước 20 phút, dose lock re-scan 30s/unlock sớm 15 phút (cả web lẫn Android) | ✅ Done | 30/08, PRs #71–#73 | 3h |
| Quocker20 | Auth/onboarding: tách gate đổi PIN khỏi onboarding, consume gate trên web+Android, exclude patient zero-dose khỏi adherence bands | ✅ Done | 28/08, PR #59 | 4h |
| Quocker20 | Redis read-through cache (medications, dashboard, adherence); fix % adherence | ✅ Done | 27/08, PRs #49/#51 | 3h |
| Quocker20 | Web doctor portal polish: prescription view, health survey (modal + patient search), alerts view localize, realtime emergency alert modal | ✅ Done | 30/08 | 5h |
| AnhVQ / Binh Minh Dao / haxuanson | Review & merge PR #34–#77 | ✅ Done | ~40 PR merge | 3h |

**Tổng kết:** Tuần dày nhất dự án: hệ thống chạy production thật (deploy, DNS, APK ký số), adherence review 7 stage hoàn chỉnh, offline-first Android. Nhiều fix migration heads do hai nhánh lớn đụng DB cùng lúc.

---

## Week 36 (31/08 – 01/09): Guardrail chat, planning agent 2.0, ổn định production

| Member | Task | Status | Output | Time |
|--------|------|--------|--------|------|
| Son | Planning Agent 2.0: bỏ LLM grouping, sinh lịch 100% deterministic (`expand_schedule` thuần rule), viết lại 4 test grouping | ✅ Done | Commit `da54613` + `06b9e71` | 6h |
| Son | Fix bug: chat history trả 500; write step bị drop trong multi-tool plan (guard `write_not_composable`); conflict check reschedule miss window vắt nửa đêm (so datetime theo timezone bệnh nhân + `asyncio.gather`); verdict "Có"/"CÓ" không khớp prefix (normalize bỏ dấu Unicode) | ✅ Done | Commit `06b9e71` | 4h |
| Son | API lịch sử hội thoại: `list_conversations()` (cache Redis) + `get_conversation_detail()` (check ownership → 403), cursor pagination, schemas nhận camelCase/snake_case; classify intent mở rộng từ khóa tác dụng phụ + trích tên thuốc | ✅ Done | `router.py`, `schemas.py`, `service.py`, `classify_intent_node.py` | 4h |
| Son | Android release v1.4.0 (chat history) → v1.5.0 build 7 (launcher icon, banner update sideload); fix null error khi kê đơn; docs planning agent | ✅ Done | 31/08, PR #86; `docs/planning-agent-features.md` | 5h |
| Kizo-pito | Guardrail scope chat: chặn tin nhắn xúc phạm, redirect khẩn cấp sang SOS, chặn out-of-scope ngữ nghĩa trước planner | ✅ Done | Commits `41e13c8`→`396327a` (01/09) | 4h |
| Kizo-pito | Chat: xác nhận trước khi đọc/reschedule lịch tương lai; khôi phục lịch sử durable + ngữ cảnh thuốc verify; adverse event bắt buộc xác nhận triệu chứng | ✅ Done | 31/08 | 6h |
| Quocker20 | PDF export đơn thuốc đã duyệt (NotoSans); dark-mode phủ chat/survey/dose; SOS modal bắt buộc xem chi tiết; dọn adverse-events-card | ✅ Done | 01/09, PRs #89–#93 | 6h |
| Quocker20 | Fix adherence review: crash job đêm + idempotent-replay không match ở production | ✅ Done | 31/08, PRs #87/#88 | 2h |
| AnhVQ / Binh Minh Dao / haxuanson | Review & merge PR #78–#94 (develop → main ở #94) | ✅ Done | | 1h |

**Tổng kết ngày 01/09:** Chốt phương hướng planning agent — sinh lịch 100% deterministic, LLM chỉ ở lớp hiểu ý; guardrail scope chặn được mọi nỗ lực dụ LLM ra ngoài phạm vi nhắc thuốc.

---

<!-- Format: mỗi tuần một bảng. Copy block trên cho các tuần tiếp theo. -->
