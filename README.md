# 🤖 AI20K Agent Template

Template chính thức cho học viên **VinUni AI20K Build Phase** — cung cấp sẵn cấu trúc dự án, code mẫu, và hướng dẫn kỹ thuật chi tiết để xây dựng AI Agent đạt điểm cao (35+/50).

> 📖 **Technical Guidebook:** [phoenix.note.transformerlabs.ai/technical-book](https://phoenix.note.transformerlabs.ai/technical-book)

## 🎯 Template này dùng để làm gì?

Khi tham gia AI20K Build Phase, mỗi đội cần xây dựng một AI Agent hoàn chỉnh — từ kiến trúc, code, test, đến deploy. Thay vì bắt đầu từ con số không, template này cung cấp:

- **Cấu trúc thư mục chuẩn** — đã được thiết kế theo best practices (separation of concerns)
- **Code mẫu** cho các phần cốt lõi: LangGraph agent, FastAPI API, config, schemas
- **Docker + CI/CD sẵn** — Dockerfile multi-stage, GitHub Actions workflow
- **Hướng dẫn kỹ thuật 10 chương** — từ clone template đến nộp bài Demo Day
- **Checklist 10 deliverables** — đảm bảo không bỏ sót yêu cầu BTC
- **AI Usage Logging tự động** — Pre-configured hooks cho Claude Code, Cursor, Codex, Gemini CLI, Antigravity, và GitHub Copilot

## ⚡ Quick Start

### Bước 1: Fork hoặc Clone

```bash
# Clone template
git clone https://github.com/AI20K-Build-Cohort-2/starter-code-template.git team-YOUR_TEAM_NAME
cd team-YOUR_TEAM_NAME

# Xóa git history cũ và khởi tạo lại
rm -rf .git
git init
git add .
git commit -m "feat: khởi tạo dự án từ template"
```

### Bước 2: Setup môi trường

```bash
# Tạo virtual environment
python3.11 -m venv .venv
source .venv/bin/activate

# Cài dependencies
pip install -e ".[dev]"

# Cấu hình API keys
cp .env.example .env
# Mở .env và thêm OPENAI_API_KEY của bạn
# Đồng thời cập nhật AI_LOG_API_KEY bằng key riêng từ link mời của BTC
# (giá trị trong .env.example chỉ là placeholder)
```

### Bước 3: Cài AI Logging Hooks

```bash
# Linux / macOS / Git Bash
bash scripts/setup_hooks.sh

# Windows PowerShell
# powershell -ExecutionPolicy Bypass -File scripts\setup_hooks.ps1
```

Hooks tự động log mọi AI prompt khi dùng Claude Code, Cursor, Codex, Gemini CLI, Antigravity, hoặc GitHub Copilot. Không cần thao tác thủ công.

### Bước 4: Chạy hạ tầng (Postgres + Redis)

```bash
docker compose up -d postgres redis
```

Lần đầu chạy, Postgres tự nạp `docs/database_v1_init.sql` (25 bảng) từ
`docker-entrypoint-initdb.d`. Việc này **chỉ xảy ra khi volume còn trống** — nếu
`p-216_postgres_data` đã tồn tại từ trước, container bỏ qua bước init.

Đưa schema lên bản mới nhất:

```bash
alembic upgrade head
```

Nếu DB được tạo bằng `database_v1_init.sql` mà chưa có bảng `alembic_version`,
đánh dấu baseline trước (chỉ làm một lần):

```bash
alembic stamp 0001_baseline
```

> `.env` dùng hostname phía **host** (`localhost`) để `pytest`/`alembic`/`uvicorn`
> chạy được ngoài container. Container `backend`/`worker` tự ghi đè thành
> `postgres`/`redis` trong `docker-compose.yml` — đừng đổi `.env` về hostname
> nội bộ Docker, sẽ làm test ngoài container mất kết nối.

### Bước 5: Chạy server

```bash
# Chạy FastAPI backend
uvicorn src.main:app --reload --port 8000

# Mở Swagger UI
# http://localhost:8000/docs
```

### Bước 6: Chạy test

```bash
pytest -q
```

Cần Postgres ở Bước 4 đang chạy — các test của slice 3/4 ghi/xoá dữ liệu thật.
Test tự dọn sau mỗi case nên chạy lại nhiều lần vẫn xanh.

### Bước 7: Đọc hướng dẫn

📖 Mở **[Technical Guidebook](https://phoenix.note.transformerlabs.ai/technical-book)** và làm theo từng chương.

## 📁 Cấu trúc dự án

> Cây thư mục thật của repo RemindRx (P-216) — không phải cây thư mục gốc của
> template AI20K. Xem [ARCHITECTURE.md](ARCHITECTURE.md) để biết chi tiết kiến
> trúc/data flow, và [CLAUDE.md](CLAUDE.md) cho quy ước + ràng buộc bắt buộc.

```
├── src/
│   ├── agents/             # 🧠 LangGraph Agent
│   │   ├── graph.py        #    State graph (nodes + edges)
│   │   ├── state.py        #    State schema (TypedDict)
│   │   ├── nodes/          #    Node functions
│   │   └── tools/          #    Agent tools (@tool)
│   ├── core/               # ⚙️ Hạ tầng dùng chung (Config, Database, Security, Redis, Celery)
│   │   ├── config.py       #    Pydantic settings đọc .env
│   │   ├── database.py     #    Async SQLAlchemy 2.0 Engine & Session
│   │   ├── redis.py        #    Redis connection pool
│   │   ├── security.py     #    Phone OTP, JWT encode/decode, RBAC guards
│   │   ├── response.py     #    Standardized API response envelope format
│   │   └── celery_app.py   #    Celery app instance
│   ├── common/             # 🛠️ Shared utilities, exceptions & middleware
│   ├── modules/            # 🧩 Phân hệ nghiệp vụ dạng Vertical Slice
│   │   ├── auth/           #    Phân hệ 1: Phone OTP & JWT Token [MẪU MODULAR]
│   │   │   ├── models.py   #    ORM Models (User, OtpCode, RefreshToken)
│   │   │   ├── router.py   #    API Endpoints (/auth/otp/request, /auth/otp/verify,...)
│   │   │   ├── service.py  #    Business Logic (Tạo OTP, Verify, Dispatch SMS)
│   │   │   └── schemas.py  #    Pydantic DTOs (OTPRequest, OTPVerify, TokenResponse)
│   │   ├── doctors/        #    Phân hệ 2: Doctor profiles & Audit logs
│   │   ├── patients/       #    Phân hệ 3 & 4: Patient profiles, routines & caregivers
│   │   ├── prescriptions/  #    Phân hệ 5: Thuốc & Đơn thuốc
│   │   ├── agents/         #    Phân hệ 6: LangGraph AI Agent & Scheduled Doses
│   │   ├── adherence/      #    Phân hệ 7: Điểm danh & SOS Red Alert
│   │   └── ocr_rag/        #    Phân hệ 8: Prescription OCR & RAG Search
│   ├── api/                # 🌐 Dependencies & Aggregated API Routers
│   │   ├── deps.py         #    Global FastAPI Dependencies (get_db, get_current_user, RBAC)
│   │   └── v1_router.py    #    Tổng hợp tất cả router từ các modules
│   └── main.py             # 🚀 FastAPI Entrypoint & WebSocket Handler
├── tests/                # 🧪 pytest suite
│   ├── test_agents/      #    Agent/graph tests
│   └── test_api/         #    API endpoint tests
├── scripts/              # 🔌 AI Logging Hooks
│   ├── log_hook.py       #    Auto-log cho Claude/Cursor/Codex/Gemini/Copilot
│   ├── log_antigravity.py#    Antigravity IDE prompt scanner
│   ├── log_manual.py     #    Manual log cho ChatGPT / web tools
│   ├── submit_log.py     #    Submit logs on git push
│   └── setup_hooks.sh    #    One-time hook installer
├── .claude/ .codex/ .cursor/ .gemini/  # Per-tool hook configs
├── .agents/              # Antigravity rules + workflows
├── .ai-log/              # 📊 AI usage logs (auto-generated)
├── docs/
│   ├── RemindRx_Tong_Hop_Tai_Lieu.md   # 📖 Brief/PRD/API Spec/Architecture/Dataset — ĐỌC TRƯỚC khi code feature
│   ├── Android_Compose_System_Design_Skills.md
│   ├── architecture_diagram.md
│   └── guide/             #    Technical Guidebook AI20K (10 chương, tài liệu chung)
├── scripts/              # 🔌 AI Logging Hooks (bắt buộc theo BTC AI20K — không xóa/sửa)
│   ├── log_hook.py        #    Auto-log cho Claude/Cursor/Codex/Gemini/Copilot
│   ├── log_antigravity.py #    Antigravity IDE prompt scanner
│   ├── log_manual.py      #    Manual log cho ChatGPT / web tools
│   ├── submit_log.py      #    Submit logs on git push (BATCH_LIMIT/lần)
│   └── setup_hooks.sh / setup_hooks.ps1  # One-time hook installer
├── .claude/               # Claude Code config cho repo này
│   ├── agents/hitl-guardrail-reviewer.md #  Review diff chạm prescription/schedule/dose
│   ├── commands/           #  /check, /new-fr
│   └── skills/             #  sync-fr-status, android-development
├── .codex/ .cursor/ .gemini/  # Per-tool hook configs (tương đương .claude/)
├── .ai-log/               # 📊 AI usage logs (auto-generated, archive/ theo ngày)
├── eval/results/          # 📊 Evaluation results
├── presentation/          # 🎤 Demo Day slides
├── outputs/               # 🗂️ Sản phẩm phụ trợ (phân tích, UI export...)
├── .github/workflows/      # ⚡ CI/CD (GitHub Actions)
├── .github/hooks/          # 🪝 Copilot hook config
├── Dockerfile              # 🐳 Multi-stage build (backend)
├── docker-compose.yml      # 🐙 Full stack orchestration
├── ARCHITECTURE.md / JOURNAL.md / WORKLOG.md  # Tài liệu nhóm tự cập nhật thủ công
├── CLAUDE.md               # Quy ước + ràng buộc bắt buộc khi code trong repo này
└── README_boilerplate.md   # 📝 README template gốc của AI20K (tham khảo, không phải README thật)
```

## 📚 Technical Guidebook — 10 Chương

| Chương | Nội dung | Thời gian |
|---------|----------|-----------|
| 1 | Lời mở đầu — Mục tiêu, cách sử dụng | 15 phút |
| 2 | Khởi tạo dự án — Clone, setup, git workflow | 4 giờ |
| 3 | Thiết kế kiến trúc — 3-tier, diagrams, ADR | 6 giờ |
| 4 | **LangGraph Agent** — State, nodes, edges, tools, RAG | 8 giờ |
| 5 | FastAPI — Routes, validation, error handling, streaming | 6 giờ |
| 6 | Giao diện — Next.js + Streamlit quickstart | 6 giờ |
| 7 | DevOps — Docker, CI/CD, deploy, logging | 6 giờ |
| 8 | Kiểm thử — Unit test, integration test, RAGAS | 4 giờ |
| 9 | Demo Day — 10 deliverables, checklist, tips | 2 giờ |
| 10 | Tài nguyên — Khóa học, docs, BMAD method | tham khảo |

📖 **Đọc online:** [phoenix.note.transformerlabs.ai/technical-book](https://phoenix.note.transformerlabs.ai/technical-book)

## 📋 10 Deliverables cho Demo Day

| # | Deliverable | File vị trí | Template có sẵn |
|---|-------------|-------------|:---:|
| 1 | Source Code | `src/` | ✅ |
| 2 | README.md | `README_boilerplate.md` → copy thành `README.md` | ✅ |
| 3 | Architecture Diagram | `docs/architecture_diagram.md` | ✅ |
| 4 | AI Logs | LangSmith (3 env vars) + Auto AI Usage Logging | ✅ |
| 5 | Live URL | Deploy lên Render/Vercel | ⚡ CI/CD sẵn |
| 6 | Video Demo | `presentation/` | 📝 |
| 7 | Pitch Deck | `presentation/` | 📝 |
| 8 | Development Journal | `JOURNAL.md` | ✅ |
| 9 | Worklog | `WORKLOG.md` | ✅ |
| 10 | Evaluation Evidence | `eval/` | 📝 |

## 🛠 Tech Stack

| Layer | Technology | Version |
|-------|-----------|---------|
| AI Agent | LangGraph + LangChain | Latest |
| Backend | FastAPI + Uvicorn | 0.100+ |
| LLM | OpenAI GPT-4o-mini | API |
| Frontend | Next.js / Streamlit | 14+ / 1.30+ |
| Database | SQLite (dev) / PostgreSQL (prod) | — |
| DevOps | Docker + GitHub Actions | — |
| Testing | pytest + pytest-asyncio | 8+ |

## 📊 AI Usage Logging

Template đã tích hợp sẵn auto-logging hooks cho 6 AI tools:

| Tool | Cơ chế | Config |
|------|--------|--------|
| Claude Code | `.claude/settings.json` hooks | Tự động |
| Cursor | `.cursor/hooks.json` | Tự động |
| OpenAI Codex CLI | `.codex/hooks.json` | Tự động |
| Gemini CLI | `.gemini/settings.json` | Tự động |
| GitHub Copilot | `.github/hooks/hooks.json` | Tự động |
| Antigravity IDE | Pre-push scan transcript | Tự động trên `git push` |

Tất cả prompts và tool calls được log vào `.ai-log/session.jsonl` và tự động submit lên grading server mỗi khi `git push`.

**ChatGPT / web tools khác** — log thủ công:
```bash
bash scripts/_pyrun.sh scripts/log_manual.py --tool chatgpt --prompt "What you asked"
```

> ⚠️ Chạy `bash scripts/setup_hooks.sh` một lần sau khi clone để cài pre-push hook.

## 📖 Đọc Technical Guidebook

**Online (khuyến nghị):** [phoenix.note.transformerlabs.ai/technical-book](https://phoenix.note.transformerlabs.ai/technical-book)

Đăng nhập bằng GitHub (cùng account đã được BTC mời vào org `AI20K-Build-Cohort-2`)
→ chọn tab **Technical Book** ở sidebar trái → đọc 10 chương + topic sections,
có table of contents bên phải, hỗ trợ light/dark/cyberpunk theme.

**Offline:** mọi chương đều ở thư mục `docs/guide/` trong template này — mở bằng
bất kỳ markdown viewer/editor nào (VS Code, Obsidian, GitHub UI, …).

## 🔗 Liên kết

- 📖 **Technical Guidebook:** [phoenix.note.transformerlabs.ai/technical-book](https://phoenix.note.transformerlabs.ai/technical-book)
- 🏫 **AI20K Program:** VinUni AI20K Build Phase
- 👨‍🏫 **Mentor:** Đặng Hải Lộc

## 📄 License

MIT — Sử dụng tự do cho mục đích giáo dục.
