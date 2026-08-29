# 💊 RemindRx (P-216) — AI Agent Hỗ Trợ Quản Lý & Nhắc Nhở Uống Thuốc

Hệ thống **RemindRx** thuộc dự án **VinUni AI20K Build Phase (Cohort 3 - Team P-216)**. Đây là giải pháp AI Agent toàn diện tích hợp backend FastAPI (LangGraph agent, Postgres, Redis, Celery) và ứng dụng di động Android (Jetpack Compose).

---

## 🎯 Bài Toán & Giải Pháp (Problem & Solution)

- **Bài toán (Problem):** Người bệnh (đặc biệt là người lớn tuổi hoặc bệnh nhân mãn tính) thường gặp khó khăn trong việc nhớ lịch uống thuốc, uống sai liều, hoặc không nhận biết sớm các tác dụng phụ nguy hiểm. Đồng thời, bác sĩ và người thân thiếu công cụ giám sát tuân thủ điều trị theo thời gian thực.
- **Giải pháp (Solution):** **RemindRx** cung cấp trợ lý AI Agent thông minh:
  - 🗣 **Tương tác Đa phương thức:** Hỗ trợ trò chuyện bằng văn bản và giọng nói tiếng Việt tự nhiên (`/chat`, `/chat/voice`).
  - ⏰ **Nhắc thuốc thông minh:** Tự động quy đổi lịch uống thuốc theo thời gian sinh hoạt cá nhân của bệnh nhân (thức dậy, ăn sáng/trưa/tối, đi ngủ).
  - 📋 **Điểm danh & Theo dõi:** Ghi nhận nhật ký uống thuốc (`TAKEN`, `SNOOZE`, `SKIPPED`) với cơ chế Idempotency-Key chống trùng lặp.
  - 🚨 **Cảnh báo an toàn & SOS:** Tự động phát hiện triệu chứng nghiêm trọng và gửi thông báo khẩn cấp SOS tới bác sĩ & người thân.

---

## 📑 Mục Lục

1. [🎯 Bài Toán & Giải Pháp (Problem & Solution)](#-bài-toán--giải-pháp-problem--solution)
2. [⚡ Quick Start & Hướng Dẫn Setup](#-quick-start--hướng-dẫn-setup)
   - [Backend Infrastructure (FastAPI + Postgres + Redis)](#1-backend-infrastructure-fastapi--postgres--redis)
   - [Android Application Setup (Android Studio)](#2-android-application-setup-android-studio)
3. [🔐 Cấu Hình Biến Môi Trường (.env)](#-cấu-hình-biến-môi-trường-env)
4. [📡 Sample Queries & Gọi API Mẫu](#-sample-queries--gọi-api-mẫu)
   - [API cURL & Python Snippets](#1-api-curl--python-snippets)
   - [Database SQL Queries Mẫu](#2-database-sql-queries-mẫu)
5. [📁 Cấu Trúc Dự Án & Tech Stack](#-cấu-trúc-dự-án--tech-stack)
6. [📊 AI Usage Logging](#-ai-usage-logging)
7. [📋 Deliverables & Tài Liệu Tham Khảo](#-deliverables--tài-liệu-tham-khảo)

---

## ⚡ Quick Start & Hướng Dẫn Setup

### 1. Backend Infrastructure (FastAPI + Postgres + Redis)

#### Bước 1: Clone Repository & Setup Virtual Environment

```bash
git clone https://github.com/AI20K-Build-Phase-Cohort-3/P-216.git
cd P-216

# Tạo virtual environment Python 3.11
python -m venv .venv

# Activate virtual environment
# Windows PowerShell:
.venv\Scripts\Activate.ps1
# Linux / macOS:
# source .venv/bin/activate

# Cài đặt dependencies
pip install -e ".[dev]"
```

#### Bước 2: Cấu hình File `.env`

```bash
cp .env.example .env
# Mở file .env để cấu hình OPENAI_API_KEY, JWT_SECRET_KEY, DB credentials,...
```

#### Bước 3: Chạy Hạ Tầng (Postgres + Redis)

```bash
docker compose up -d postgres redis
```

Lần đầu khởi chạy, Postgres tự động nạp schema từ `docs/database_v1_init.sql` (21 bảng).

Đồng bộ Alembic migration lên bản mới nhất:

```bash
# Đánh dấu baseline nếu chưa có alembic_version (làm một lần đầu)
alembic stamp 0001_baseline

# Migration
alembic upgrade head
```

Migration `0016_seed_medications` tự nạp 66 hoạt chất nền vào PostgreSQL (không
ghi vào Chroma/RAG). Có thể chủ động nạp/cập nhật lại bằng:

```bash
python scripts/seed_medications.py
```

Script upsert theo `source_name + source_record_key`, nên có thể chạy lại an
toàn mà không tạo thuốc trùng. Dùng `--dry-run` để chỉ kiểm tra file catalog.

#### Bước 4: Chạy Server FastAPI

```bash
uvicorn src.main:app --reload --port 8000
```
- Swagger UI Documentation: `http://localhost:8000/docs`
- Health check API: `http://localhost:8000/health`

#### Bước 5: Chạy Unit & Integration Test

```bash
pytest -q
```

---

### 2. Android Application Setup (Android Studio)

Tài liệu này hướng dẫn chạy ứng dụng Android **RemindRx** trên máy cá nhân bằng Android Studio (hỗ trợ Windows, macOS, Linux).

#### 🛠 Yêu Cầu Tiên Quyết
- **Git**
- **Android Studio** (bản ổn định gần nhất)
- **JDK 17** (có thể dùng Embedded JDK 17 đi kèm Android Studio)
- **Android SDK Platform 34** và **Android SDK Build-Tools**
- **Android Emulator** (API 34+)

> Dự án đã có Gradle Wrapper, không cần tự cài Gradle riêng.

#### 🚀 Các Bước Thực Hiện

##### 1. Mở Đúng Thư Mục Project
1. Mở Android Studio và chọn **Open**.
2. Trỏ đến thư mục **`P-216/android`** (chú ý: **không** mở thư mục gốc `P-216`).
   ```text
   P-216/
   └── android/                <- Mở thư mục này bằng Android Studio
       ├── settings.gradle.kts
       ├── build.gradle.kts
       ├── gradlew.bat
       └── app/
   ```
3. Chờ Android Studio hoàn tất **Gradle Sync** (lần đầu có thể mất vài phút).

##### 2. Cài Đặt Android SDK (nếu được yêu cầu)
1. Vào **Tools → SDK Manager**.
2. Trong tab **SDK Platforms**, tích chọn cài **Android API 34**.
3. Trong tab **SDK Tools**, bảo đảm tích chọn:
   - Android SDK Build-Tools
   - Android SDK Platform-Tools
   - Android Emulator
4. Nhấn **Apply**, sau đó thực hiện **File → Sync Project with Gradle Files**.

##### 3. Tạo và Khởi Động Emulator
1. Vào **Tools → Device Manager**.
2. Chọn **Create device**, chọn mẫu thiết bị (ví dụ Pixel) và nhấn **Next**.
3. Chọn system image có **API 34 trở lên**.
4. Khởi động emulator bằng cách nhấn nút Play (`▶`).

##### 4. Chạy Ứng Dụng
1. Trên thanh công cụ Android Studio, chọn Run Configuration: **`app`**.
2. Chọn Android Emulator vừa khởi động.
3. Nhấn nút **Run** (`▶`) hoặc dùng phím tắt `Shift + F10`.

##### 🔗 Kết Nối Backend & Tài Khoản Demo
- Debug build trên Android Emulator được cấu hình gọi backend qua địa chỉ:
  ```text
  http://10.0.2.2:8000/api/v1/
  ```
  *(10.0.2.2 là loopback IP đặc biệt để Emulator truy cập localhost của máy tính host).*
- **Tài khoản Demo (Debug Mode):**
  - **Số điện thoại:** `0900000000`
  - **PIN ban đầu:** `123456`

##### 🚨 Lỗi Thường Gặp (Troubleshooting)

| Sự cố | Nguyên nhân & Cách khắc phục |
| --- | --- |
| **Không nhận project Gradle** | Mở nhầm thư mục gốc `P-216`. Đóng project và mở lại đúng thư mục **`P-216/android`** (nơi chứa `settings.gradle.kts`). |
| **Lỗi Java / JDK Version** | Vào `Settings → Build, Execution, Deployment → Build Tools → Gradle`. Mục **Gradle JDK**, chọn **Embedded JDK 17**, sau đó Sync lại. |
| **App không gọi được API** | Kiểm tra Backend FastAPI có đang chạy trên host port `8000` hay không. Lưu ý Emulator dùng `10.0.2.2`, không dùng `localhost`. |
| **Gradle Sync Fails do mạng** | Tắt **Offline work** trong Gradle Settings và chạy `File → Sync Project with Gradle Files`. |

---

## 🔐 Cấu Hình Biến Môi Trường (.env)

Chi tiết các biến cấu hình trong file `.env` (tham khảo mẫu tại `.env.example`):

| Nhóm Cấu Hình | Biến Môi Trường | Mô Tả & Giá Trị Mẫu |
| --- | --- | --- |
| **Security & JWT** | `JWT_SECRET_KEY` | Chuỗi bí mật mã hóa JWT (VD: `remindrx_dev_secret_key_...`) |
| | `JWT_ALGORITHM` | Thuật toán mã hóa JWT (`HS256`) |
| | `ACCESS_TOKEN_EXPIRE_MINUTES` | Thời gian hết hạn Access Token (phút, mặc định: `30`) |
| | `REFRESH_TOKEN_EXPIRE_DAYS` | Thời gian hết hạn Refresh Token (ngày, mặc định: `7`) |
| | `PASSWORD_PEPPER` | Chuỗi pepper gia tăng bảo mật PIN/mật khẩu |
| **LLM Provider** | `OPENAI_API_KEY` | API Key OpenAI cho LangGraph Agent (VD: `sk-proj-...`) |
| | `ANTHROPIC_API_KEY` | (Tùy chọn) API Key Anthropic Claude |
| | `GOOGLE_API_KEY` | (Tùy chọn) API Key Google Gemini |
| **Database** | `POSTGRES_USER` | Username PostgreSQL (`remindrx`) |
| | `POSTGRES_PASSWORD` | Password PostgreSQL (`secret`) |
| | `POSTGRES_DB` | Tên Database PostgreSQL (`remindrx_db`) |
| | `DATABASE_URL` | Async Connection String (VD: `postgresql+asyncpg://remindrx:secret@localhost:5432/remindrx_db`) |
| **Redis & Broker** | `REDIS_HOST` / `REDIS_PORT` | Host (`localhost` hoặc `redis`) và Port (`6379`) |
| | `REDIS_URL` | Connection URL Redis (`redis://localhost:6379/0`) |
| | `CELERY_BROKER_URL` | Connection string cho Celery Task Queue |
| **Vector Store** | `CHROMA_PERSIST_DIR` | Thư mục lưu trữ vector database RAG (`./data/chroma`) |
| **Backend API** | `APP_HOST` / `APP_PORT` | Host (`0.0.0.0`) & Port (`8000`) cho FastAPI server |
| | `CORS_ORIGINS` | Danh sách domain được phép gọi API (VD: `http://localhost:3000,http://localhost:5173`) |
| **Speech (STT/TTS)** | `STT_MODEL` / `TTS_MODEL` | Model Whisper STT & TTS cho endpoint `/chat/voice` |
| **AI Logging** | `AI_LOG_SERVER` | Server nhận log AI Usage (`https://ai-logs.note.transformerlabs.ai/api/ingest`) |
| | `AI_LOG_API_KEY` | API key cấp bởi BTC AI20K |

---

## 📡 Sample Queries & Gọi API Mẫu

### 1. API cURL & Python Snippets

#### A. Đăng Nhập (`POST /api/v1/auth/login`)

**cURL:**
```bash
curl -X POST "http://localhost:8000/api/v1/auth/login" \
     -H "Content-Type: application/json" \
     -d '{
       "phone": "0900000000",
       "password": "123456"
     }'
```

**Python:**
```python
import requests

url = "http://localhost:8000/api/v1/auth/login"
payload = {"phone": "0900000000", "password": "123456"}
response = requests.post(url, json=payload)
print(response.json())
```

#### B. Trò Chuyện Với AI Agent (`POST /api/v1/chat`)

**cURL:**
```bash
curl -X POST "http://localhost:8000/api/v1/chat" \
     -H "Content-Type: application/json" \
     -d '{
       "message": "Tôi vừa uống 1 viên Paracetamol lúc 7h sáng",
       "patient_id": "b3f1a2c3-4d5e-6f7a-8b9c-0d1e2f3a4b5c"
     }'
```

**Python:**
```python
import requests

url = "http://localhost:8000/api/v1/chat"
payload = {
    "message": "Tôi cảm thấy chóng mặt sau khi uống thuốc",
    "patient_id": "b3f1a2c3-4d5e-6f7a-8b9c-0d1e2f3a4b5c"
}
res = requests.post(url, json=payload)
print("AI Response:", res.json()["response"])
```

#### C. Điểm Danh Nhắc Thuốc (`POST /api/v1/scheduled-doses/{id}/actions`)

**cURL:**
```bash
curl -X POST "http://localhost:8000/api/v1/scheduled-doses/9a8b7c6d-5e4f-3a2b-1c0d-9e8f7a6b5c4d/actions" \
     -H "Authorization: Bearer <YOUR_ACCESS_TOKEN>" \
     -H "Idempotency-Key: dose-action-20260816-01" \
     -H "Content-Type: application/json" \
     -d '{
       "action": "TAKEN",
       "action_source": "PATIENT_MOBILE_APP"
     }'
```

#### D. Kích Hoạt Cảnh Báo SOS (`POST /api/v1/patients/{id}/sos`)

**cURL:**
```bash
curl -X POST "http://localhost:8000/api/v1/patients/b3f1a2c3-4d5e-6f7a-8b9c-0d1e2f3a4b5c/sos" \
     -H "Authorization: Bearer <YOUR_ACCESS_TOKEN>" \
     -H "Idempotency-Key: sos-trigger-20260816-01" \
     -H "Content-Type: application/json" \
     -d '{
       "message": "Chóng mặt và tức ngực cấp tính",
       "metadata": {"lat": 10.762622, "lng": 106.660172}
     }'
```

---

### 2. Database SQL Queries Mẫu

Dưới đây là một số truy vấn SQL hữu ích để kiểm tra dữ liệu trực tiếp trong PostgreSQL container:

```bash
# Đăng nhập vào Postgres Container
docker exec -it remindrx_postgres psql -U remindrx -d remindrx_db
```

#### Truy vấn 1: Danh sách tài khoản người dùng & Vai trò
```sql
SELECT id, phone, role, status, created_at 
FROM users 
ORDER BY created_at DESC 
LIMIT 10;
```

#### Truy vấn 2: Danh sách đơn thuốc đang có hiệu lực (ACTIVE)
```sql
SELECT p.id AS prescription_id, p.patient_id, u.phone AS patient_phone, p.status, p.created_at
FROM prescriptions p
JOIN users u ON p.patient_id = u.id
WHERE p.status = 'ACTIVE';
```

#### Truy vấn 3: Lịch sử uống thuốc (Adherence Logs) mới nhất
```sql
SELECT al.id, al.patient_id, al.scheduled_dose_id, al.action, al.performed_at, al.action_source
FROM adherence_logs al
ORDER BY al.performed_at DESC
LIMIT 10;
```

#### Truy vấn 4: Các cảnh báo an toàn & SOS đang mở (OPEN)
```sql
SELECT id, patient_id, alert_type, severity, status, message, created_at
FROM alerts
WHERE status = 'OPEN'
ORDER BY created_at DESC;
```

---

## 📁 Cấu Trúc Dự Án & Tech Stack

```text
P-216/
├── android/                    # 📱 Core Mobile App (Jetpack Compose, Kotlin)
│   ├── app/                    #    Android app module
│   ├── build.gradle.kts        #    Root Gradle config
│   └── settings.gradle.kts     #    Gradle settings
├── src/                        # 🧠 Backend & AI Agent (FastAPI + LangGraph)
│   ├── agents/                 #    LangGraph State, Nodes, Edges & Tools
│   ├── core/                   #    Config, Database, Security, Redis, Celery
│   ├── modules/                #    Vertical Slice Modules:
│   │   ├── auth/               #      - Auth (JWT, OTP)
│   │   ├── doctors/            #      - Doctor profile & Audit logs
│   │   ├── patients/           #      - Patient profile & Routine
│   │   ├── prescriptions/      #      - Prescriptions & Items
│   │   ├── adherence/          #      - Adherence logs & SOS Alerts
│   │   └── ocr_rag/            #      - OCR & RAG search
│   ├── api/                    #    Global Routers & Dependencies
│   └── main.py                 #    FastAPI Entrypoint & WebSockets
├── tests/                      # 🧪 Pytest Suite (API & Agent tests)
├── docs/                       # 📖 Tài liệu PRD, Database Spec & Guidebooks
├── scripts/                    # 🔌 AI Logging Hooks (setup_hooks.sh, log_hook.py)
├── docker-compose.yml          # 🐙 Orchestration (Backend, Postgres, Redis)
├── Dockerfile                  # 🐳 Multi-stage container build
└── api.md                      # 📡 Chi tiết API Specification
```

### 🛠 Tech Stack
- **AI Agent:** LangGraph, LangChain, OpenAI GPT-4o-mini / ChromaDB (RAG)
- **Backend:** FastAPI, Python 3.11, Async SQLAlchemy 2.0, Alembic, Celery, Redis
- **Mobile App:** Kotlin, Android SDK 34, Jetpack Compose, Retrofit
- **Database:** PostgreSQL 15, Redis 7
- **DevOps & Tools:** Docker, Docker Compose, Pytest, GitHub Actions

---

## 📊 AI Usage Logging

Dự án tích hợp sẵn hệ thống **Auto AI Usage Logging** theo yêu cầu của BTC AI20K:

```bash
# Cài đặt hooks tự động (Linux / macOS / Git Bash)
bash scripts/setup_hooks.sh

# Windows PowerShell:
# powershell -ExecutionPolicy Bypass -File scripts\setup_hooks.ps1
```

Hooks sẽ tự động quét và thu thập log prompt từ các công cụ AI (Claude Code, Cursor, Codex, Gemini CLI, Antigravity) lưu tại `.ai-log/session.jsonl` và đồng bộ lên server khi `git push`.

---

## 📋 Deliverables & Tài Liệu Tham Khảo

- 📖 **Technical Guidebook:** [phoenix.note.transformerlabs.ai/technical-book](https://phoenix.note.transformerlabs.ai/technical-book)
- 📡 **Full API Specification:** [api.md](api.md)
- 🏗 **Architecture Documentation:** [ARCHITECTURE.md](ARCHITECTURE.md)
- 📐 **Database Schema:** [schema.md](schema.md)

---

## 📄 License

MIT — AI20K Build Phase Cohort 3 (P-216 Team).
