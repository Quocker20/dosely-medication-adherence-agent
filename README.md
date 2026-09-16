# 💊 RemindRx — Medication Adherence AI Platform

> **One-sentence Summary:** A multi-agent AI system that empowers chronic patients to adhere to medication schedules and enables real-time treatment safety monitoring under Human-in-the-loop (doctor) oversight.

[![Python](https://img.shields.io/badge/Python-3.11%20%7C%203.12-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![LangGraph](https://img.shields.io/badge/AI%20Agent-LangGraph-FF6F00?logo=langchain&logoColor=white)](https://www.langchain.com/langgraph)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15-4169E1?logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![Redis](https://img.shields.io/badge/Redis-7-DC382D?logo=redis&logoColor=white)](https://redis.io/)
[![Android](https://img.shields.io/badge/Android-SDK%2034-3DDC84?logo=android&logoColor=white)](https://developer.android.com/)
[![React](https://img.shields.io/badge/Web%20Portal-React%2018%20%2B%20Vite-61DAFB?logo=react&logoColor=black)](https://vitejs.dev/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

---

## 📑 Table of Contents

1. [🎯 Problem & Solution](#-problem--solution)
2. [👥 Target Users](#-target-users)
3. [🧠 AI Agent & System Architecture](#-ai-agent--system-architecture)
4. [🛠 Tech Stack](#-tech-stack)
5. [⚡ Quick Start & Development Setup](#-quick-start--development-setup)
   - [A. Backend Infrastructure (FastAPI + PostgreSQL + Redis)](#a-backend-infrastructure-fastapi--postgresql--redis)
   - [B. Web Doctor/Caregiver Portal (React + Vite)](#b-web-doctorcaregiver-portal-react--vite)
   - [C. Android Mobile Application (Jetpack Compose)](#c-android-mobile-application-jetpack-compose)
6. [🔐 Environment Variables (.env)](#-environment-variables-env)
7. [🧪 Testing & AI Evaluation (Benchmark)](#-testing--ai-evaluation-benchmark)
8. [📡 Sample Queries & API Usage](#-sample-queries--api-usage)
9. [📁 Project Directory Structure](#-project-directory-structure)
10. [📋 Deliverables Checklist](#-deliverables-checklist)
11. [👥 Team Members](#-team-members)
12. [🙏 Acknowledgements](#-acknowledgements)
13. [📄 License](#-license)

---

## 🎯 Problem & Solution

### Problem
Outpatients with chronic conditions (hypertension, diabetes, cardiovascular diseases, elderly patients) face significant clinical challenges:
- **Missed Doses & Irregular Timing:** Chronic disease treatment non-adherence rates reach up to 50% (WHO), leading to avoidable complications and emergency readmissions.
- **Drug Interactions & Side Effects:** Patients often alter dosages on their own or take conflicting medications without timely clinical guidance when experiencing adverse reactions.
- **Lack of Doctor-Caregiver Visibility:** Clinicians lack objective visibility into patient adherence between scheduled appointments, while family caregivers lack reliable remote monitoring tools.

### Solution
**RemindRx** bridges this gap with an integrated dual-agent AI architecture spanning mobile and web portals:
- 🗣 **Multi-modal Chat Agent:** Natural Vietnamese voice and text dialogue (`/chat`, `/chat/voice`), answering drug interaction questions and explaining prescriptions using a RAG knowledge base indexed from the Vietnam National Drug Formulary.
- ⏰ **Personalized Schedule Planning Agent:** Intelligently translates medical prescriptions into personalized intake schedules aligned with the patient's biological daily routine (waking time, meals, bedtime).
- 🛡 **Deterministic Safety & Guardrail Engine:** Strictly blocks unauthorized dose alterations or medication discontinuation requests via chat. Enforces Human-in-the-Loop (doctor approval) prior to persisting schedule changes.
- 🚨 **Real-time Red Alerts & SOS:** Detects critical symptoms and triggers emergency notifications to the Doctor Portal and designated family caregivers.

---

## 👥 Target Users

| Role | User Group | Key Responsibilities & Capabilities |
| :--- | :--- | :--- |
| **Primary** | **Patients** | Mobile App interaction: receive dose reminders, record intake (`TAKEN`/`SNOOZE`/`SKIPPED`), interact with voice/text AI assistant, trigger SOS alerts. |
| **Secondary** | **Doctors / Healthcare Providers** | Web Portal: prescribe medications, review and approve AI-generated intake schedules, track adherence scores, and triage clinical SOS alerts. |
| **Secondary** | **Caregivers / Family Members** | Web/App: monitor daily intake compliance reports and receive alerts when multiple consecutive doses are missed. |
| **Admin** | **System Administrators** | Web Portal: user account provisioning, role management, audit log monitoring, and AI usage governance. |

---

## 🧠 AI Agent & System Architecture

RemindRx follows a **Modular Monolith** architecture combined with **Dual LangGraph Agents** guarded by **Strict Deterministic Code Validators**:

```mermaid
graph TB
    subgraph Clients["Clients Layer"]
        Web["💻 Web Portal (React + Vite)\nDoctor / Caregiver / Admin SPA"]
        And["📱 Android App (Kotlin + Compose)\nPatient App (Offline-cache Room + Sync)"]
    end

    subgraph Gateway["API Gateway & Security"]
        API["FastAPI App (:8000 /api/v1)\nJWT Auth + RBAC + Idempotency"]
        RateLimit["Rate Limiter (Redis)"]
    end

    subgraph Agents["AI Agent Layer (LangGraph)"]
        ChatAgent["🗣 Chat Agent (agents/graph.py)\nDrug inquiry & Patient interaction"]
        PlanAgent["📅 Planning Agent (agents/planning_graph.py)\nRoutine-aware Schedule Generation"]
        Guardrail["🛡 Safety Guardrail\nBlocks dose changes / Hallucinations"]
        RAG["📚 Drug Formulary RAG\nChromaDB (11.6k chunks Formulary)"]
    end

    subgraph Validation["Deterministic Code Gate (HITL)"]
        Consistency["Prescription Consistency Checker\n(Python Deterministic Code, NOT LLM)"]
        DoctorReview["👨‍⚕️ Doctor HITL Approval Node"]
    end

    subgraph Storage["Data & Infrastructure"]
        Postgres[("🐘 PostgreSQL (Asyncpg)\n21 relational tables + Audit Logs")]
        RedisDB[("⚡ Redis\nCache & Broker")]
        CeleryWorker["⏰ Celery Worker & Beat\nSchedule Scanner & Push Dispatcher"]
    end

    Web -->|"HTTPS REST"| API
    And -->|"HTTPS REST + WebSocket"| API
    API --> RateLimit
    API --> Guardrail
    Guardrail --> ChatAgent
    ChatAgent --> RAG
    API --> PlanAgent
    PlanAgent --> Consistency
    Consistency --> DoctorReview
    DoctorReview -->|"Doctor Approval Required"| Postgres
    CeleryWorker --> RedisDB
    CeleryWorker --> Postgres
```

### Invariant Safety Principles (Agent Guardrails)
1. **Human-in-the-Loop (HITL):** Only licensed physicians can create, modify, or approve clinical prescriptions and dosage changes.
2. **Deterministic Code Gate:** Schedules suggested by the Planning Agent must pass a pure Python validator (verifying intervals, maximum daily dosage, and drug conflicts) before persistence.
3. **Medical Policy Enforcement:** The Chat Agent is programmatically restricted from recommending dosage modifications, discontinuation, or substitute drugs.

---

## 🛠 Tech Stack

| Layer | Technology | Details |
| :--- | :--- | :--- |
| **AI Agents & RAG** | **LangGraph**, **LangChain**, **OpenAI GPT-4o-mini**, **ChromaDB** | Decoupled Chat & Planning state graphs; national drug formulary RAG vector store |
| **Speech Processing** | **OpenAI Whisper** & **TTS Engine** | Vietnamese Speech-to-Text and Text-to-Speech pipeline for elderly users |
| **Backend** | **FastAPI**, **Python 3.11/3.12**, **Pydantic v2** | Modular asynchronous architecture with vertical business slices |
| **Database & ORM** | **PostgreSQL 15**, **SQLAlchemy 2.0 (Async)**, **Alembic** | Relational data persistence with service-level transaction boundaries |
| **Task Queue & Cache** | **Redis 7**, **Celery Worker & Beat** | Scheduled reminder engine, notification dispatching, and rate limiting |
| **Web Portal** | **React 18**, **TypeScript**, **Vite** | Multi-role portal for doctors and caregivers |
| **Mobile Application** | **Android (Kotlin)**, **Jetpack Compose**, **Room**, **Retrofit** | Patient client with local offline database and outbox sync mechanism |
| **DevOps & QA** | **Docker**, **Docker Compose**, **Pytest**, **GitHub Actions** | Container orchestration, automated testing, and CI pipeline |

---

## ⚡ Quick Start & Development Setup

### Prerequisites
- **Python 3.11+**
- **Docker & Docker Compose**
- **Node.js 18+** & `npm` (for Web Portal)
- **Android Studio** (Iguana / Jellyfish) with JDK 17 & Android SDK 34 (for Mobile App)

---

### A. Backend Infrastructure (FastAPI + PostgreSQL + Redis)

#### 1. Clone Repository & Setup Python Virtual Environment
```bash
git clone https://github.com/AI20K-Build-Phase-Cohort-3/P-216.git
cd P-216

# Create virtual environment
python -m venv .venv

# Activate virtual environment
# Windows PowerShell:
.venv\Scripts\Activate.ps1
# Linux / macOS:
# source .venv/bin/activate

# Install development dependencies
pip install -e ".[dev]"
```

#### 2. Configure Environment Variables
```bash
cp .env.example .env
# Edit .env to set OPENAI_API_KEY, JWT_SECRET_KEY, DATABASE_URL, etc.
```

#### 3. Start Database & Broker Containers (Docker)
```bash
docker compose up -d postgres redis
```

#### 4. Run Migrations & Seed Medication Catalog
```bash
# Stamp baseline migration (first time only)
alembic stamp 0001_baseline

# Apply migrations
alembic upgrade head

# Seed initial formulary medications (66 core active substances)
python scripts/seed_medications.py
```

#### 5. Launch FastAPI Backend Server
```bash
uvicorn src.main:app --reload --port 8000
```
- 📖 **Interactive Swagger Docs:** `http://localhost:8000/docs`
- 💓 **Health Check Endpoint:** `http://localhost:8000/health`

---

### B. Web Doctor/Caregiver Portal (React + Vite)

The management portal for clinicians and caregivers is located in `web/`:

```bash
cd web

# Install dependencies
npm install

# Start development server
npm run dev
```
- Access the web interface at: `http://localhost:5173`
- Pre-configured to communicate with the backend at `http://localhost:8000/api/v1`

---

### C. Android Mobile Application (Jetpack Compose)

1. Launch **Android Studio**, select **Open**, and browse directly to **`P-216/android`** *(Important: Do not open the root directory)*.
2. Allow Android Studio to complete **Gradle Sync**.
3. Create and launch an Android Virtual Device (Recommended: **Pixel 6/7 with API 34+**).
4. Click **Run (`Shift + F10`)** to compile and launch the application.

> **Network Note:** The Android emulator reaches the host backend via `http://10.0.2.2:8000/api/v1/`.  
> **Demo Account:** Phone: `0900000000` | PIN: `123456`.

---

## 🔐 Environment Variables (.env)

| Variable Name | Sample Value | Description |
| :--- | :--- | :--- |
| `JWT_SECRET_KEY` | `remindrx_super_secret_dev_key_p216` | Secret key for signing access and refresh JWT tokens |
| `PASSWORD_PEPPER` | `custom_pepper_string` | Pepper string for password and PIN hashing |
| `DATABASE_URL` | `postgresql+asyncpg://remindrx:secret@localhost:5432/remindrx_db` | Asynchronous PostgreSQL connection string |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis connection URL for caching and Celery broker |
| `OPENAI_API_KEY` | `sk-proj-...` | API key for LangGraph agents and embeddings |
| `CHROMA_PERSIST_DIR` | `./data/chroma` | Persistence directory for RAG vector index |
| `AI_LOG_SERVER` | `https://ai-logs.note.transformerlabs.ai/api/ingest` | Centralized AI usage telemetry server |
| `AI_LOG_API_KEY` | *(Assigned by AI20K)* | Telemetry authentication key |

---

## 🧪 Testing & AI Evaluation (Benchmark)

### 1. Automated Unit & Integration Tests
```bash
# Run complete test suite (400+ unit and integration tests)
pytest -q

# Run specific adherence & safety review tests
pytest tests/test_api/test_adherence_reviews.py
```

### 2. AI Agent Evaluation & Benchmarks
The `eval/` directory contains curated golden datasets and benchmarking harnesses:
```bash
# Evaluate 50 clinical safety guardrail test cases
python eval/run_guardrail_50_live.py

# Evaluate personalized routine schedule extraction accuracy
python eval/rescheduling_extract_eval.py

# Evaluate RAG retrieval quality (Faithfulness, Relevance, Groundedness)
python eval/hybrid_chat_eval.py
```
> Evaluation outputs and metrics are automatically saved under `eval/results/`.

---

## 📡 Sample Queries & API Usage

### 1. User Authentication (`POST /api/v1/auth/login`)
```bash
curl -X POST "http://localhost:8000/api/v1/auth/login" \
     -H "Content-Type: application/json" \
     -d '{
       "phone": "0900000000",
       "password": "123456"
     }'
```

### 2. Medication Inquiry via AI Agent (`POST /api/v1/chat`)
```bash
curl -X POST "http://localhost:8000/api/v1/chat" \
     -H "Authorization: Bearer <TOKEN>" \
     -H "Content-Type: application/json" \
     -d '{
       "message": "I experienced dizziness after taking Amlodipine, is this normal?",
       "patient_id": "b3f1a2c3-4d5e-6f7a-8b9c-0d1e2f3a4b5c"
     }'
```

### 3. Record Dose Intake Action (`POST /api/v1/scheduled-doses/{id}/actions`)
```bash
curl -X POST "http://localhost:8000/api/v1/scheduled-doses/9a8b7c6d-5e4f-3a2b-1c0d-9e8f7a6b5c4d/actions" \
     -H "Authorization: Bearer <TOKEN>" \
     -H "Idempotency-Key: dose-action-20260902-01" \
     -H "Content-Type: application/json" \
     -d '{
       "action": "TAKEN",
       "action_source": "PATIENT_MOBILE_APP"
     }'
```

---

## 📁 Project Directory Structure

```text
P-216/
├── android/                    # 📱 Client 1: Android Mobile App (Kotlin + Compose)
│   ├── app/src/main/java/      #    UI Features, Room DB, Retrofit API Client
│   └── build.gradle.kts        #    Gradle build configurations (SDK 34)
├── web/                        # 💻 Client 2: Doctor & Caregiver Portal (React + Vite)
│   ├── src/                    #    SPA Pages (Doctor Dashboard, Prescriptions, Caregivers)
│   └── package.json            #    TypeScript + Vite scripts
├── src/                        # 🧠 Core Backend & AI Agent (FastAPI Modular Architecture)
│   ├── agents/                 #    LangGraph Chat Agent, Planning Agent & Policy Enforcers
│   ├── core/                   #    Configs, Async Database Engine, Security & Envelopes
│   ├── modules/                #    Vertical Business Domains:
│   │   ├── auth/               #      - Authentication, JWT, PIN & RBAC
│   │   ├── patients/           #      - Patient Profiles & Routine Management
│   │   ├── doctor/             #      - Doctor Directory & Clinical Permissions
│   │   ├── prescriptions/      #      - Prescription Management & PDF Export
│   │   ├── adherence/          #      - Intake Logging, Check-ins & Idempotency
│   │   ├── adherence_review/   #      - Clinical Adherence Auditing
│   │   ├── dashboard/          #      - Realtime Dashboard & WebSocket Metrics
│   │   └── agents/             #      - Schedule Planner API Integration
│   ├── rag_retrieval/          #    ChromaDB Retriever for National Drug Formulary
│   └── main.py                 #    FastAPI App Entrypoint & Router Registry
├── eval/                       # 📊 AI Benchmark & Evaluation Suite (Golden datasets)
│   ├── results/                #    Benchmarking logs and accuracy reports
│   └── hybrid_chat_eval.py     #    Evaluation script for RAG & Chat Agent
├── docs/                       # 📖 PRD, Database Specifications & API Contracts
│   ├── api-contract.md         #    Standardized API Response Contract
│   └── ARCHITECTURE.md         #    In-depth Architecture Blueprint
├── tests/                      # 🧪 Test Suite (Pytest Unit, Integration & Mock tests)
├── docker-compose.yml          # 🐳 PostgreSQL + Redis infrastructure
└── pyproject.toml              # 📦 Dependency management & project metadata
```

---

## 📋 Deliverables Checklist

- [x] **Source Code:** Complete codebase for FastAPI Backend, React Web Portal, and Android Client.
- [x] **Documentation:** Thorough README and architectural reference documentation.
- [x] **Architecture Diagram:** Detailed system and agent flow in [ARCHITECTURE.md](ARCHITECTURE.md).
- [x] **API Specification:** Documented in [docs/api-contract.md](docs/api-contract.md) and [docs/api-reference.md](docs/api-reference.md).
- [x] **AI Evaluation Suite:** Test cases and benchmark scripts in `eval/`.
- [x] **AI Usage Telemetry:** Integrated telemetry hooks in `.ai-log/` syncing to AI20K server.
- [x] **Demonstration Video:** Available via [Google Drive (RemindRx Demo Video)](https://drive.google.com/file/d/1TgBhlN7OH6psTQeFFrCcQ9398X4Dea4i/view?usp=sharing).
- [x] **Pitch Deck & Presentation:** Available online via [Google Slides (RemindRx Pitch Deck)](https://docs.google.com/presentation/d/15ktC7J-78AhfC5JhMdvT11pFVXYros2Z3ioBOv5dU3E/edit?usp=sharing).

---

## 👥 Team Members

**Group 07 – Team 216** (Project Mentor: **Mr. Văn Hữu Quốc** — *Project Direction & Healthcare Solution Architecture Advisor*):

| # | Member Name | Role Title | Key Contributions |
| :---: | :--- | :--- | :--- |
| 1 | **Hà Xuân Sơn** | Lead Frontend & Mobile / DevOps | • UI/UX Web & Mobile<br>• Android APK & SQLite DB<br>• Adaptive Planning Agent<br>• Full Production Deploy |
| 2 | **Vũ Quốc Anh** | Lead Backend / AI Engineer | • Core API & Database Arc<br>• Adherence Monitoring Agent<br>• Telegram Bot Subsystem<br>• UI/UX Optimization & Server Deployment Support |
| 3 | **Đào Bình Minh** | AI Chatbot Engineer | • Vector Database Deployment<br>• AI Chatbot Development<br>• Tool Calling & Medical RAG |
| 4 | **Nguyễn Đức Đạt** | Developer | • Push Notification System |

---

## 🙏 Acknowledgements

Team 216 would like to express our deepest gratitude to:
- **The Program Organizing Committee** and mentor **Mr. Văn Hữu Quốc** for creating a meaningful academic platform, providing dedicated mentorship, and giving attentive guidance and direction throughout the project lifecycle, and **The Panel of Judges** for taking the time to listen to the team's presentation.
- In addition, the team would like to express our sincere thanks to **Viện Dưỡng lão Diên Hồng (Cơ sở 6)** and **Mr. Nguyễn Quốc Huy** for providing valuable information, surveys, and professional medical support for the project.

---

## 📄 License

Distributed under the **MIT License** — Copyright © 2026 **Team P-216 (VinUni AI20K Build Phase Cohort 3)**.
