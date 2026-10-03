# Dosely (VMEC-04) — Tổng hợp toàn bộ tài liệu dự án

> Nguồn: (1) Ảnh đề bài gốc do mentor cấp — "AI Agent Nhắc Thuốc & Theo Dõi Tuân Thủ Điều Trị"; (2) Toàn bộ 12 file trong Google Drive folder "AI thực chiến SU 2026" (đọc trực tiếp ngày 05/08/2026). Mã đề tài **VMEC-04**, giai đoạn **G1 — Chốt đề tài**.
>
> Tài liệu Drive **chính là bản triển khai chi tiết của đề bài** — không phải nguồn tham khảo khác. Sản phẩm được đặt tên **Dosely** (tên gọi trước đó trong một số file cũ là **AdhereMind**).

---

## 0. Danh sách file đã đọc

| # | File | Loại | Kích thước | Trạng thái đọc |
|---|------|------|-----------|----------------|
| 1 | Dosely_Brief.docx | Word | 13 KB | Đầy đủ (3 trang) |
| 2 | Dosely_PRD.docx | Word | 16 KB | Đầy đủ (5 trang) |
| 3 | Dosely_API_Specification_v1.0.docx | Word | 44 KB | Đầy đủ (9 trang) |
| 4 | Dosely_System_Architecture_Document_v1.0.docx | Word | 1.5 MB | Đầy đủ (22 trang) |
| 5 | Dosely_Dataset_Acquisition_and_Integration_Spec_v1.0.docx | Word | 42 KB | Đầy đủ (4 trang) |
| 6 | AdhereMind_MVP_Features_Specification_v2.pdf | PDF | 78 KB | Đầy đủ (2 trang) — bản đặc tả cũ, tên FR khác |
| 7 | AdhereMind_GitHub_AI_Log_Setup.md.pdf | PDF | 20 KB | Giới hạn — file là ảnh chụp màn hình trang GitHub, không có lớp văn bản để trích xuất |
| 8 | T216_project_management_document.xlsx | Excel | 67 KB | Đầy đủ — nhưng nội dung phần lớn là **template rỗng**, chưa điền |
| 9 | AdhereMind_Wireframe_1_BenhNhan.png | Ảnh | 93 KB | Không xem được nội dung hình ảnh trong phiên này (giới hạn công cụ trình duyệt — không chụp được ảnh màn hình) |
| 10 | AdhereMind_Wireframe_2_TuongTac.png | Ảnh | 128 KB | Như trên |
| 11 | AdhereMind_Wireframe_3_Alert_BacSi.png | Ảnh | 149 KB | Như trên |
| 12 | Dosely_ERD_Detailed_v1.1_Visual_Layout.drawio | Diagram | 203 KB | Không có bản xem trước trong Google Drive (định dạng .drawio không hỗ trợ) — nội dung ERD được bù đắp bởi mục 6 (Data dictionary) trong System Architecture Document |

---

## 1. Đề bài gốc (ảnh mentor cấp)

**Tên đề tài:** AI Agent Nhắc Thuốc & Theo Dõi Tuân Thủ Điều Trị

**Thực trạng:** Bệnh nhân, đặc biệt người cao tuổi và mắc bệnh mạn tính, thường quên uống thuốc, uống sai liều/sai giờ, tự ý ngưng thuốc, làm giảm hiệu quả điều trị và tăng tái nhập viện.

**Vấn đề:** Cần AI Agent quản lý phác đồ dùng thuốc (từ đơn mô phỏng do bác sĩ nhập), tự lập lịch nhắc thông minh, hội thoại xác nhận đã uống, phát hiện bỏ thuốc/tác dụng phụ, và chủ động cảnh báo cho người thân/bác sĩ khi tuân thủ kém — agent lập kế hoạch tiến trình → giáo dục → escalate.

**Ràng buộc bắt buộc:** HITL bắt buộc — đơn thuốc/liều CHỈ do bác sĩ tạo và duyệt. AI KHÔNG tự kê, tự đổi liều hay khuyên ngưng thuốc; mọi thay đổi phác đồ phải bác sĩ phê duyệt. Grounded trên đơn đã duyệt + thông tin thuốc có nguồn, không tự suy diễn liều/tương tác. Bảo mật PII/PHI.

**Tech stack gợi ý (đề bài):** LLM; LangGraph agent với scheduler & vòng lặp theo dõi tuân thủ; RAG trên cơ sở dữ liệu thuốc mô phỏng (chỉ định, tác dụng phụ) + vector DB; tool reminder/notification (email/web push); adherence tracker, escalation; guardrails chặn kê đơn/liều; backend FastAPI + cron/Celery; frontend React/Next.js đăng nhập phân vai bệnh nhân/người thân/bác sĩ; Postgres; deploy cloud.

**Yêu cầu đầu ra — Cơ bản:** App deploy, ≥2 vai trò (bệnh nhân/bác sĩ, tùy chọn người thân); bác sĩ nhập & duyệt phác đồ, agent tạo lịch nhắc, hội thoại xác nhận uống thuốc và ghi nhận; hiển thị khuyến cáo & không tự đổi liều.

**Yêu cầu đầu ra — Nâng cao:** Dashboard tuân thủ (tỉ lệ, chuỗi bỏ liều); cảnh báo tác dụng phụ nghiêm trọng → escalate; HITL để bác sĩ duyệt điều chỉnh lịch; memory thói quen bệnh nhân tối ưu giờ uống; báo cáo định kỳ; xử lý khi bệnh nhân không phản hồi (nhắc lại/báo người thân).

---

## 2. Đối chiếu: đề bài ↔ những gì đã làm

| Yêu cầu đề bài | Đáp ứng trong tài liệu Dosely |
|---|---|
| ≥2 vai trò | 3 vai trò: Bác sĩ, Bệnh nhân, Người thân/Caregiver (+ role SYSTEM nội bộ) |
| Bác sĩ nhập & duyệt phác đồ | FR-1.1 E-Prescription, workflow DRAFT→APPROVED, HITL bắt buộc |
| Agent tạo lịch nhắc | FR-2.1 Planning Agent (LangGraph) |
| Hội thoại xác nhận uống thuốc | FR-3.1 Reminder & Compliance Logging (3 trạng thái: Đã uống/Uống muộn/Bỏ qua) |
| Không tự đổi liều | Guardrail cứng: Rescheduling Agent chỉ dời giờ, validator code chặn AI đổi dose/frequency |
| Dashboard tuân thủ | FR-1.2 Compliance & Alert Dashboard, KPI adherence ≥70% |
| Cảnh báo tác dụng phụ → escalate | FR-4.1/FR-4.2 Side-Effect Survey + SOS + Closed-Loop Red Alert (<10s đa kênh) |
| HITL duyệt điều chỉnh lịch | Prescription/Schedule versioning, mọi thay đổi phác đồ qua bác sĩ |
| Memory thói quen bệnh nhân | patient_routines (giờ ăn/ngủ) dùng làm input cho Planning/Rescheduling Agent |
| Báo cáo định kỳ | Adherence aggregate, KPI instrumentation (mục 12 System Architecture) |
| Xử lý khi không phản hồi | Worker đánh dấu MISSED sau 60 phút không TAKEN → consecutive miss counter → escalation |
| RAG dược điển | FR-3.2 OCR & RAG (Kaggle "11000 Medicine Details" dataset, không phải dược điển chính thức Việt Nam — xem mục 6) |
| Backend FastAPI + Celery | Đúng như đề bài |
| Frontend React | React PWA (không dùng Next.js) |
| Postgres | Đúng như đề bài |

**Điểm vượt đề bài:** OCR nhận diện vỏ thuốc (chụp ảnh), WebSocket realtime dashboard, event-driven architecture (outbox pattern), SLO/observability chi tiết, data dictionary 15 bảng, API contract đầy đủ (OpenAPI + Postman).

**Điểm chưa làm / cắt khỏi MVP:** Tự động phát hiện tương tác thuốc chéo (DDI), tích hợp HIS/EMR, ký số đơn thuốc, đa ngôn ngữ, chế độ offline đầy đủ.

---

## 3. Bài toán & Giải pháp (Dosely_Brief.docx)

**Thực trạng:** WHO ước tính ~50% bệnh nhân mạn tính không tuân thủ điều trị → giảm hiệu quả, tăng biến chứng, tăng tái nhập viện và chi phí y tế.

**Vấn đề cốt lõi:** Thiếu hệ thống kết nối liên tục giữa Bác sĩ và Bệnh nhân sau khi rời phòng khám.

**Giải pháp — Dosely:** Web-App (PWA) dùng AI Agent để (1) tự động lập lịch uống thuốc tối ưu từ đơn điện tử + lịch sinh hoạt cá nhân, (2) nhắc nhở qua Web Push Notification với tương tác 1 chạm, (3) giám sát tuân thủ real-time và báo động khẩn cấp cho người thân/bác sĩ khi phát hiện sự cố.

### Đối tượng sử dụng
| Vai trò | Nhu cầu chính |
|---|---|
| Bác sĩ điều trị | Kê đơn điện tử, theo dõi tuân thủ qua Dashboard |
| Bệnh nhân | Nhận nhắc nhở, xác nhận uống thuốc, báo triệu chứng |
| Người thân/con cháu | Nhận cảnh báo SMS/Zalo khi bệnh nhân bỏ thuốc hoặc có sự cố |

---

## 4. Tầm nhìn & Phạm vi (Dosely_PRD.docx)

**Tầm nhìn:** Xây dựng cầu nối kỹ thuật số liên tục giữa Bác sĩ và Bệnh nhân sau khi rời phòng khám, tối ưu hóa tuân thủ điều trị thông qua AI Agent — giảm tái nhập viện, giảm biến chứng, nâng cao chất lượng cuộc sống.

**Đối tượng bệnh nhân mục tiêu:** Bệnh nhân mạn tính cần tuân thủ phác đồ dài hạn — tiểu đường, tăng huyết áp, tim mạch, COPD, suy thận... Đặc biệt hữu ích cho bệnh nhân dùng đa thuốc (≥3 loại/ngày) — nhóm nguy cơ tuân thủ kém cao nhất.

**Phạm vi MVP:** Giải quyết bài toán cốt lõi — kết nối không gián đoạn Bác sĩ↔Bệnh nhân qua dữ liệu đơn thuốc điện tử an toàn 100%, loại bỏ phụ thuộc vào công nghệ xử lý ảnh (VLM) kém tin cậy cho chữ viết tay.

**Ngoài phạm vi MVP (Out of scope):**
- Tự động phát hiện tương tác thuốc chéo (DDI) khi kê đơn ("Clinical Guardrails")
- Tích hợp trực tiếp HIS/EMR
- Ký số đơn thuốc
- Đa ngôn ngữ
- Chế độ offline đầy đủ

### Persona chi tiết
| Persona | Đặc điểm | Nhu cầu chính |
|---|---|---|
| Bác sĩ điều trị | Quản lý bệnh nhân mạn tính dùng thuốc dài hạn | Kê đơn nhanh, theo dõi tuân thủ từ xa, nhận cảnh báo sự cố |
| Bệnh nhân | Mạn tính, ≥3 loại thuốc/ngày | Nhắc đúng giờ, giao diện đơn giản, tra cứu thông tin thuốc |
| Người thân/chăm sóc | Có thể không ở cùng bệnh nhân; con cháu thường setup ban đầu cho người cao tuổi | Nhận thông báo khẩn khi bỏ thuốc/tác dụng phụ nghiêm trọng |

---

## 5. Tính năng MVP — chuẩn hóa theo 4 phân hệ (FR Coding Rules)

Quy tắc mã hóa: **FR-1.x** Medical Portal | **FR-2.x** AI Engine | **FR-3.x** Patient PWA | **FR-4.x** Safety & Escalation

### FR-1.x — Phân hệ Bác sĩ & Portal Quản trị
| Mã | Tính năng | Mô tả | Đầu ra |
|---|---|---|---|
| FR-1.1 | Kê đơn thuốc điện tử | Autocomplete từ DB dược phẩm, cấu hình liều/thời điểm uống. HITL bắt buộc — bác sĩ duyệt mọi đơn | Đơn thuốc JSON chuẩn hóa |
| FR-1.2 | Dashboard giám sát tuân thủ & cảnh báo | Theo dõi tỷ lệ tuân thủ real-time, nhãn đỏ khi bỏ thuốc/triệu chứng bất thường | Giao diện Dashboard |

### FR-2.x — Phân hệ AI Agent Core & Lập lịch
| Mã | Tính năng | Mô tả | Đầu ra |
|---|---|---|---|
| FR-2.1 | Planning Agent (AI Scheduler) | Tính khung giờ nhắc thuốc cá nhân hóa từ đơn đã duyệt + lịch sinh hoạt (giờ ăn/ngủ) | Lịch nhắc uống thuốc (Timeline) |
| FR-2.2 | Rescheduling Agent | Tự động dời/tính lại cữ thuốc khi uống muộn hoặc đổi giờ ăn/ngủ, đảm bảo khoảng cách an toàn giữa liều | Schedule cập nhật động |

### FR-3.x — Phân hệ Bệnh nhân & Tương tác (Patient PWA)
| Mã | Tính năng | Mô tả | Đầu ra |
|---|---|---|---|
| FR-3.1 | Nhắc nhở & ghi nhận tuân thủ | Web Push/Zalo, 3 nút [Đã uống]/[Uống muộn]/[Bỏ qua] | Adherence Logs |
| FR-3.2 | OCR & RAG nhãn thuốc | Chụp nhãn thuốc → OCR bóc tách hoạt chất + RAG dược điển tóm tắt công dụng | Thẻ thông tin thuốc |

### FR-4.x — Phân hệ An toàn Y khoa & Escalation
| Mã | Tính năng | Mô tả | Đầu ra |
|---|---|---|---|
| FR-4.1 | Khảo sát tác dụng phụ & SOS | Khảo sát triệu chứng cuối ngày + nút SOS 1 chạm | Báo cáo triệu chứng / Red Alert trigger |
| FR-4.2 | Closed-Loop Red Alert | Tự động escalate khi bỏ thuốc >3 lần liên tiếp hoặc SOS/triệu chứng nguy hiểm → SMS/Zalo/Call người thân + Portal bác sĩ, đa kênh <10 giây | Escalation workflow |

> **Lưu ý lịch sử:** Bản đặc tả cũ hơn (`AdhereMind_MVP_Features_Specification_v2.pdf`, tên dự án cũ AdhereMind) dùng đánh số FR-1.1→FR-5.2 tuyến tính (không phân theo 4 phân hệ), nội dung tương đương nhưng có thêm chi tiết nghiệp vụ: quy trình xử lý sự cố mô tả cụ thể "bỏ thuốc quá 3 lần → Celery task tự động gọi SMS/Zalo", "tác dụng phụ nghiêm trọng → Call bot + màn hình hướng dẫn sơ cứu tại chỗ". Bản Dosely sau này là bản đã tái cấu trúc/chuẩn hóa lại.

---

## 6. Tech Stack

| Lớp | Công nghệ |
|---|---|
| Frontend | React PWA |
| Backend | FastAPI + Celery + Redis |
| AI | LangGraph (Planning Agent, Rescheduling Agent) + RAG (dược điển) + vector DB |
| OCR | PaddleOCR / VietOCR |
| Database | PostgreSQL |
| Deploy | Cloud (chưa chốt nhà cung cấp) |

### Nguyên tắc kiến trúc cốt lõi (System Architecture §2.3)
- **Safety before convenience:** khi dữ liệu thiếu/xung đột/không lập lịch hợp lệ được → giữ trạng thái an toàn, yêu cầu review, KHÔNG tự suy đoán.
- **Deterministic core, AI-assisted planning:** LLM/agent chỉ đề xuất; quy tắc dose/frequency/spacing luôn được kiểm tra bằng code xác định (không phải AI).
- **Version everything clinical:** Prescription/routine/schedule đều có version + effective time, không sửa đè lịch sử.
- **Idempotent events, Least privilege, Observable by default.**

---

## 7. Kiến trúc hệ thống (Dosely_System_Architecture_Document_v1.0.docx — 22 trang)

### 7.1. Mô hình tổng thể
Modular monolith: một FastAPI deployment chứa các module nghiệp vụ biên rõ ràng (Prescription, Schedule, Adherence, Safety, Notification, Drug Info), kết hợp Celery workers xử lý nền và LangGraph orchestration cho agent. Giảm độ phức tạp vận hành ở giai đoạn MVP, vẫn có đường tách microservices khi tải tăng.

| Thành phần | Trách nhiệm | Giao tiếp |
|---|---|---|
| React Medical Portal | Kê/duyệt đơn, dashboard, xử lý cảnh báo | REST, WebSocket |
| React Patient PWA | OTP, routine, reminders, adherence action, survey, SOS, OCR upload | REST, Web Push, WebSocket/SSE |
| FastAPI | Auth/RBAC, validation, domain orchestration, event publishing | HTTPS JSON; WSS |
| Celery + Redis | Job nhắc thuốc, timeout, retry, escalation, aggregation | Redis broker/backend |
| LangGraph Agents | Planning & Rescheduling theo state graph | Internal API/job; JSON |
| PostgreSQL | System of record | SQL/ORM; migrations |
| External providers | OTP, Web Push, SMS/Zalo/Call | Provider APIs; signed callbacks |

### 7.2. Kiến trúc AI Agent (LangGraph)
LangGraph dùng như **state machine có kiểm soát**, KHÔNG phải chatbot tự do. Mỗi run: Input Gate → Normalize → Generate Candidate → Deterministic Validate → Apply Notification Grouping → Persist → Audit.

**Guardrails bắt buộc:**
- Chỉ đọc prescription có `status=APPROVED`.
- Output phải tuân JSON Schema; cấm text tự do ghi lịch trực tiếp.
- Validator bằng code là cổng cuối cùng — agent không được bypass.
- KHÔNG có thao tác UPDATE dose/frequency/route/treatment duration từ agent.
- Xung đột không giải được → `NEEDS_REVIEW`, không tự tạo lịch mới.
- Mọi run lưu model/version, prompt version, input/output hash, latency, lỗi.

**Failure modes & fallback:**
| Tình huống | Xử lý an toàn |
|---|---|
| Agent timeout/model unavailable | Retry giới hạn → fallback deterministic scheduler → nếu không, NEEDS_REVIEW |
| Output sai schema | Reject, retry 1 lần với repair node, không persist output lỗi |
| Không đảm bảo khoảng cách liều | Giữ lịch hiện tại, đánh dấu conflict, hướng dẫn liên hệ bác sĩ |
| Routine đổi sát giờ uống | Khóa theo patient, xử lý serial, bảo toàn dose đang in-progress |
| Race reminder vs reschedule | Schedule version + optimistic concurrency |

### 7.3. Data Flow (6 luồng chính)
DF-01 Kê đơn → DF-02 Lập lịch → DF-03 Nhắc/tuân thủ → DF-04 Dời lịch → DF-05 Safety escalation → DF-06 OCR/RAG.

### 7.4. Data Dictionary (15 bảng chính, PostgreSQL)
`users`, `doctor_profiles`, `patient_profiles`, `caregiver_links`, `prescriptions`, `prescription_items`, `patient_routines`, `medication_schedules`, `scheduled_doses`, `adherence_logs`, `notification_deliveries`, `health_surveys`/`symptom_reports`, `alerts`/`alert_events`, `agent_runs`, `drug_catalog`/`knowledge_chunks`, `audit_logs`.

**State machines:**
- Prescription: `DRAFT → APPROVED → SUPERSEDED | ENDED | CANCELLED`
- Schedule: `GENERATING → ACTIVE → SUPERSEDED | FAILED | NEEDS_REVIEW`
- ScheduledDose: `PENDING → SENT → TAKEN | LATE | SKIPPED | MISSED | CANCELLED`
- Alert: `OPEN → ACKNOWLEDGED → ESCALATING → RESOLVED | CLOSED_FALSE_POSITIVE`
- Notification: `QUEUED → SENT → DELIVERED | FAILED → RETRYING | DEAD_LETTER`

### 7.5. Luồng nghiệp vụ trọng yếu
**Reminder & tuân thủ:** Celery job thức dậy trước `scheduled_at` → gửi Web Push/Zalo (idempotency key) → PWA ghi AdherenceLog append-only → nếu không TAKEN trong 60 phút, worker đánh dấu MISSED + tăng consecutive-miss counter → Dashboard nhận update realtime.

**Closed-loop Red Alert:** Trigger = 3 lần SKIPPED/MISSED liên tiếp trong ngày, HOẶC SOS, HOẶC symptom severity=SEVERE → tạo Alert OPEN (transaction) → gửi đồng thời/theo priority tới caregiver (SMS/Zalo/Call) + Portal bác sĩ → retry exponential backoff, dead-letter khi quá ngưỡng → Alert chỉ RESOLVED khi actor hợp lệ xác nhận, toàn bộ audit.

> **OPEN DECISION chưa chốt:** Brief ghi "bỏ thuốc >3 lần liên tiếp", PRD ghi "3 lần liên tiếp" — baseline áp dụng theo PRD (3 lần), cần Product/Clinical owner xác nhận lại.

### 7.6. Bảo mật, riêng tư & an toàn y khoa
**Threat model tóm tắt:**
| Rủi ro | Kiểm soát |
|---|---|
| Chiếm đoạt OTP/token | Rate limit theo phone/IP/device, OTP TTL + one-time use, refresh rotation |
| Bác sĩ truy cập bệnh nhân không thuộc quyền | RBAC + relationship/organization authorization mọi endpoint, audit deny |
| Sửa prescription sau duyệt | Immutability theo version; chỉ tạo version mới |
| Gửi nhắc/cảnh báo trùng | Idempotency keys, unique constraints, callback dedup |
| Prompt injection qua OCR/RAG | OCR text là dữ liệu không tin cậy; retrieval allowlist; ảnh không được điều khiển tool/agent |
| Rò rỉ PII/PHI qua log | Structured logging + redaction, cấm log body nhạy cảm |
| Agent bịa thông tin lâm sàng | Grounded data, JSON schema, deterministic validator, source refs, HITL |

**Retention:** Prescription/schedule/adherence/alert — theo chính sách y tế/pháp lý (cần legal review); OTP/session logs 30–90 ngày; ảnh OCR xóa sau xử lý hoặc tối đa 24 giờ; agent prompts/outputs chỉ lưu dữ liệu đã giảm thiểu, không gửi PHI cho provider ngoài nếu chưa có DPA.

### 7.7. SLO đề xuất
| Chỉ tiêu | Mục tiêu |
|---|---|
| API availability | ≥99.5%/tháng |
| Reminder dispatch | 95% job bắt đầu trong ±60s so với scheduled_at |
| Red Alert dispatch | Bắt đầu gửi đa kênh trong <10 giây |
| Planning Agent | <10 giây cho đơn 5–8 thuốc; timeout cứng 15 giây |
| Data durability | RPO ≤15 phút, RTO ≤4 giờ (giả định) |
| Dashboard realtime | Event xuất hiện ≤5 giây |

### 7.8. Triển khai & CI/CD
4 môi trường: Local (Docker Compose) → Development → Staging → Production (HA, managed DB/Redis, WAF/monitoring). Migration theo expand-and-contract, canary/rolling deploy, agent prompt/graph có version + golden test cases, feature flags cho OCR/Zalo/Call/escalation rules.

### 7.9. KPI (theo PRD)
| KPI | Mục tiêu | Nguồn đo |
|---|---|---|
| Adherence | ≥70% | COUNT(TAKEN)/COUNT(doses due) |
| Response time | <30 phút | action_at − notification.sent_at |
| Red Alert true positive | ≥90% | Manual review + confusion matrix |
| Planning Agent latency | <10 giây | agent_runs duration |
| Survey completion | ≥60% | completed/expected surveys |
| Onboarding | ≥80% | funnel: OTP verified → routine saved → first schedule active |

### 7.10. Giả định, quyết định mở & rủi ro chưa chốt
| ID | Loại | Nội dung |
|---|---|---|
| A-01 | ASSUMPTION | MVP dùng modular monolith, không microservices đầy đủ |
| A-02 | ASSUMPTION | Khoảng cách tối thiểu giữa liều lưu theo prescription item hoặc rule config |
| D-01 | OPEN | Ngưỡng bỏ thuốc: đúng 3 hay >3 lần liên tiếp (Brief vs PRD mâu thuẫn) |
| D-02 | OPEN | Nhà cung cấp Zalo API / Call bot chưa chọn |
| D-03 | OPEN | Caregiver có tài khoản riêng hay chỉ là recipient contact |
| D-04 | OPEN | Bác sĩ có cần MFA trong MVP không (khuyến nghị có) |
| R-01 | RISK | Quy tắc lâm sàng lập lịch chưa được PRD mô tả đủ — không hard-code suy đoán |
| R-02 | RISK | Web Push không đảm bảo delivery mọi thiết bị — cần fallback Zalo/SMS |
| R-03 | RISK | OCR nhãn thuốc có thể sai — cần confidence threshold + confirm UI |
| R-04 | RISK | Provider outage làm chậm Red Alert — cần multi-channel + circuit breaker |
| R-05 | RISK | Quy định PII/PHI theo quốc gia chưa xác định — cần legal review trước production |
| Multi-tenant | OPEN | Chưa chốt một cơ sở y tế hay nhiều cơ sở (schema đã có `organization_id` dự phòng) |

---

## 8. Đặc tả API (Dosely_API_Specification_v1.0.docx — OpenAPI 3.0 + Postman Collection)

**Base path:** `/api/v1` | **Auth:** JWT Bearer (OTP điện thoại cho bệnh nhân) | **Format:** JSON UTF-8, multipart/form-data cho ảnh

**Roles:** `PATIENT` (xem lịch của mình, ghi dose action, survey/SOS, OCR) · `DOCTOR` (quản lý đơn thuốc bệnh nhân phụ trách, dashboard, resolve alert) · `CAREGIVER` (quyền tối thiểu — chưa chốt chi tiết) · `SYSTEM` (worker nội bộ, không tạo/đổi liều)

**Quy ước:** Idempotency-Key bắt buộc cho dose action & SOS · Pagination `page`/`page_size` · ID = UUID v4 · Timestamp ISO 8601 + timezone · Error envelope có `trace_id`.

### Danh mục endpoint đầy đủ (24 endpoints, 8 module)
| Method | Path | Module | Mục đích |
|---|---|---|---|
| POST | `/auth/patient/otp/request` | Authentication | Yêu cầu OTP |
| POST | `/auth/patient/otp/verify` | Authentication | Xác thực OTP, cấp token |
| POST | `/auth/refresh` | Authentication | Làm mới access token |
| POST | `/patients/{id}/prescriptions` | Prescriptions | Tạo đơn thuốc nháp (Doctor) |
| GET | `/patients/{id}/prescriptions` | Prescriptions | Danh sách đơn thuốc |
| GET | `/prescriptions/{id}` | Prescriptions | Chi tiết đơn thuốc |
| POST | `/prescriptions/{id}/approve` | Prescriptions | Bác sĩ duyệt — HITL, phát event `PrescriptionApproved` |
| POST | `/prescriptions/{id}/cancel` | Prescriptions | Hủy đơn thuốc |
| GET/PUT | `/patients/{id}/routine` | Patient Routine | Lấy/cập nhật lịch sinh hoạt |
| POST | `/patients/{id}/schedules/generate` | Schedules & Agents | Kích hoạt Planning Agent |
| GET | `/patients/{id}/schedules` | Schedules & Agents | Lấy lịch hiện hành |
| POST | `/patients/{id}/schedules/reschedule` | Schedules & Agents | Kích hoạt Rescheduling Agent |
| GET | `/agent-runs/{id}` | Schedules & Agents | Trạng thái lần chạy agent |
| POST | `/scheduled-doses/{id}/actions` | Adherence | Ghi TAKEN/LATE/SKIPPED (idempotent) |
| GET | `/patients/{id}/adherence` | Adherence | Tổng hợp tuân thủ |
| GET | `/patients/{id}/adherence/logs` | Adherence | Nhật ký tuân thủ |
| POST | `/patients/{id}/health-surveys` | Safety | Khảo sát sức khỏe hằng ngày |
| POST | `/patients/{id}/sos` | Safety | SOS một chạm |
| GET | `/alerts` | Safety | Danh sách Red Alerts |
| POST | `/alerts/{id}/acknowledge` \| `/resolve` | Safety | Xử lý cảnh báo |
| POST | `/patients/{id}/drug-label-ocr` | OCR & RAG | Upload ảnh nhãn thuốc |
| GET | `/ocr-jobs/{id}` | OCR & RAG | Kết quả OCR + RAG |
| GET | `/dashboard/patients` \| `/dashboard/patients/{id}` | Dashboard | Danh sách/chi tiết bệnh nhân |

**WebSocket:** `GET /api/v1/ws/dashboard?access_token=<short_lived_token>` — events: `adherence.updated`, `alert.opened`, `alert.updated`, `schedule.updated`. Client phải reconnect + đồng bộ lại qua REST (WS không thay thế nguồn dữ liệu chuẩn).

**Definition of Done cho API:** Contract OpenAPI hợp lệ, không trùng operationId · Test 401/403 theo quan hệ patient-doctor · Không có endpoint nào cho AI tạo đơn/đổi liều/đổi số cữ · Idempotency replay không tạo bản ghi trùng · Concurrency: 2 reschedule đồng thời chỉ 1 version active · Planning Agent <10s cho đơn 5-8 thuốc · Log không chứa OTP/token/PHI dạng plaintext.

**Giả định cần xác nhận:** Domain server là placeholder · Cơ chế đăng nhập bác sĩ/quản trị tổ chức/caregiver invitation chưa được PRD định nghĩa đầy đủ · Provider SMS/Zalo/Call chưa chốt · Danh mục mã triệu chứng & drug catalog cần chuẩn hóa bởi Product/Medical · Không có endpoint xóa cứng dữ liệu y tế trong MVP.

---

## 9. Dataset thuốc (Dosely_Dataset_Acquisition_and_Integration_Spec_v1.0.docx)

**Nguồn:** Kaggle — "11000 Medicine Details" (chủ sở hữu Navjot Singh, web-scraped từ 1mg.com, giấy phép **CC0 Public Domain**, >11.000 bản ghi thuốc). **Đây là dataset công khai, KHÔNG phải dược điển lâm sàng chính thức của Việt Nam.**

**9 cột gốc dự kiến:** Medicine Name, Composition/Salt, Uses, Side Effects, Manufacturer, Image URL, Excellent/Average/Poor Review %.

**Cách tải:** Kaggle CLI khuyến nghị — `kaggle datasets download -d singhnavjot2062001/11000-medicine-details`, token `kaggle.json` không commit vào Git.

**Mô hình chuẩn hóa PostgreSQL (`drug_catalog`):** `drug_id` (UUID), `brand_name`, `normalized_name`, `composition_raw`, `active_ingredients` (jsonb, parser rule-based, giữ raw nếu confidence thấp), `uses_text`, `side_effects_text`, `manufacturer`, `image_url`, 3 cột `review_*_pct`, `source_name`, `source_row_hash` (SHA-256 chống trùng), `ingested_at`.

**Quy trình ETL:** Extract → Profile → Normalize → Parse composition → Deduplicate → Validate → Load (staging → merge) → Index → Audit.

**Kiểm tra chất lượng bắt buộc:** brand_name không được rỗng · review % trong khoảng 0–100 · composition parser phải có confidence score · loại bỏ HTML/script trước khi đưa vào RAG · không coi Uses/Side Effects là hướng dẫn điều trị đã xác thực tại Việt Nam.

**⚠️ Giới hạn quan trọng — dataset KHÔNG chứa:** tương tác thuốc (DDI), chống chỉ định, liều theo tuổi/cân nặng/thận-gan, thai kỳ/cho con bú, mã ATC/RxNorm/SNOMED, hướng dẫn trước/sau ăn, khoảng cách liều, giá hiện hành, hay dữ liệu thuốc được cấp phép tại Việt Nam. Các trường này **phải lấy từ nguồn dược điển được cấp phép và chuyên gia y khoa phê duyệt** — đây chính là lý do "Clinical Guardrails/DDI" bị loại khỏi phạm vi MVP.

**Phạm vi dùng trong Dosely:** Autocomplete đơn thuốc (bác sĩ vẫn phải chọn/xác nhận), OCR matching (không tự xác nhận thuốc chỉ dựa ảnh), RAG thông tin thuốc (không chẩn đoán/không tạo liều), Planning Agent (chỉ dùng để nhận dạng thuốc tham chiếu — không dùng cho lịch/khoảng cách liều), Analytics.

---

## 10. Quản lý dự án (T216_project_management_document.xlsx)

**Trạng thái:** File hiện là **template quản lý dự án chưa điền đầy đủ**, phần lớn ô còn ở dạng placeholder (`[Tên sản phẩm hoặc dự án]`, `[DD/MM/YYYY]`...).

**Cấu trúc file:**
- Thông tin dự án: tên, nhóm, ngày bắt đầu/kết thúc, trưởng nhóm, mentor, stakeholder, link GitHub, link sản phẩm live, mục tiêu 6 tuần — **chưa điền**.
- Tiến độ theo Sprint: 4 sprint (Khởi động & Thiết kế → Phát triển vòng 1 → Phát triển vòng 2 & Sửa lỗi → Hoàn thiện & Bàn giao) — tất cả đang **"Chưa bắt đầu"**.
- Chỉ số theo dõi chính: Tổng User Story = **28**, Đã hoàn thành = **0/28**, Lỗi đang mở = **1**, số lần gặp đối tác/mức hài lòng demo/tình trạng triển khai — **chưa điền**.

→ Đây là tín hiệu cho thấy tài liệu thiết kế (Brief/PRD/API/Architecture/Dataset spec) đã hoàn thành khá đầy đủ ở giai đoạn G1, nhưng việc **tracking thực thi (sprint, code, demo) chưa bắt đầu** — bước tiếp theo hợp lý là khởi tạo repo GitHub, điền hồ sơ quản lý dự án và bắt đầu Sprint 1.

---

## 11. Wireframe & ERD (chưa xem được nội dung trực quan)

3 file ảnh wireframe và 1 file ERD (.drawio) tồn tại trong Drive nhưng **không xem được nội dung hình ảnh trong phiên làm việc này** do giới hạn công cụ trình duyệt (không chụp/hiển thị được ảnh). Dựa theo tên file có thể suy luận phạm vi:

| File | Suy luận nội dung (theo tên file) |
|---|---|
| `AdhereMind_Wireframe_1_BenhNhan.png` | Màn hình chính bệnh nhân (Patient PWA) — có thể là trang chủ/lịch nhắc thuốc |
| `AdhereMind_Wireframe_2_TuongTac.png` | Màn hình tương tác — có thể là giao diện nhắc nhở với 3 nút Đã uống/Uống muộn/Bỏ qua (FR-3.1) |
| `AdhereMind_Wireframe_3_Alert_BacSi.png` | Dashboard cảnh báo phía bác sĩ (FR-1.2 / FR-4.2) |
| `Dosely_ERD_Detailed_v1.1_Visual_Layout.drawio` | Sơ đồ trực quan của 15 bảng dữ liệu — nội dung logic đã có đầy đủ dạng bảng ở mục 7.4 |

Nếu cần, có thể mở trực tiếp các file này bằng draw.io hoặc trình xem ảnh để đối chiếu với đặc tả FR ở trên.

---

## 12. Ghi chú / Log AI (AdhereMind_GitHub_AI_Log_Setup.md.pdf)

File PDF này là ảnh chụp màn hình trang GitHub, không có lớp text để trích xuất nội dung chi tiết.

---

## 13. Việc cần chốt trước khi code (tổng hợp từ tất cả các file)

1. **Ngưỡng bỏ thuốc:** 3 lần hay >3 lần liên tiếp (Brief vs PRD mâu thuẫn — Architecture doc tạm chọn 3 theo PRD).
2. **Nhà cung cấp SMS/Zalo/Call bot** — ảnh hưởng trực tiếp đến SLA Red Alert <10 giây.
3. **Mô hình tenant** — một cơ sở y tế hay nhiều cơ sở (multi-tenant).
4. **Cơ chế đăng nhập bác sĩ/quản trị tổ chức** — chưa được PRD định nghĩa đầy đủ.
5. **Caregiver có tài khoản riêng hay chỉ là recipient contact.**
6. **MFA cho bác sĩ** — khuyến nghị có nhưng chưa chốt.
7. **Danh mục mã triệu chứng chuẩn** và **drug catalog chuẩn** — cần Product/Medical xác nhận.
8. **Legal/privacy review** cho PII/PHI theo quy định Việt Nam trước khi lên production.
9. **Điền hồ sơ quản lý dự án** (T216 xlsx) và bắt đầu Sprint 1 — hiện toàn bộ tracking đang ở 0%.
10. **Repo GitHub** — cần xác nhận lại đường dẫn repo chính thức (link cũ không truy cập được).

---

*Tài liệu này tổng hợp toàn bộ nội dung đọc được từ 12 file trong Google Drive kết hợp với đề bài gốc do mentor cấp, phục vụ mục đích nắm bắt toàn cảnh dự án Dosely (VMEC-04) tại thời điểm 05/08/2026.*
