# ADHE REMIND — Backend Architecture & Project Structure Guide

> Note: "ADHE REMIND" only survives today as the internal `app_name` default in
> `src/core/config.py:16` (asserted by `tests/test_api/test_core.py:18`). The actual
> product/repo name everywhere else (README, package names, Docker container names) is
> **RemindRx**.

This document defines the modular domain-driven architecture for the **ADHE REMIND** medication adherence platform backend.

---

## 📁 System Directory Tree

```
src/
├── agents/                 # 🧠 LangGraph Agent (chat graph)
│   ├── graph.py            # State graph (nodes + edges) — safety_guard first, then classify_intent + branches/ReAct loop
│   ├── state.py            # State schema (TypedDict)
│   ├── planning_graph.py   # A SEPARATE second LangGraph — schedule/reschedule pipeline, independent of the chat graph above
│   ├── planning_state.py   # State schema for planning_graph.py
│   ├── audit.py            # Agent-run audit helpers
│   ├── medication_policy.py    # Deterministic (no-LLM) block on dose-change/stop/coadminister/prescribe requests
│   ├── patient_addressing.py   # Vietnamese respectful-address helpers
│   ├── patient_presentation.py # Patient-facing text formatting
│   ├── prescription_consistency.py # Code-level validator for prescription/schedule consistency
│   ├── nodes/              # Node functions — includes both chat nodes (classify_intent, safety_guard, drug_rag, rescheduling, ...)
│   │                       #   and the `planning_*_node.py` pipeline for planning_graph.py (input_gate, normalize,
│   │                       #   generate_candidate, lock_and_revalidate, apply_grouping, persist, audit)
│   └── tools/              # Agent tools (@tool)
│
├── rag_ingestion/          # 📥 Offline OCR/embedding pipeline for the drug-formulary RAG corpus
│   ├── pipeline.py
│   └── taxonomy.py
│
├── rag_retrieval/          # 🔎 Live drug-formulary RAG (hybrid dense+BM25, grounding/citation)
│   ├── service.py          # DrugRAG — retrieval + grounding
│   ├── safe_service.py     # SafeDrugRAG — wraps service.py with the full guardrail chain
│   ├── dense_index.py
│   ├── conversation_store.py
│   ├── input_guardrail.py  # Requires a drug name before retrieval — no broad semantic search
│   └── language_guardrail.py
│
├── core/                   # ⚙️ Infrastructure & Shared Platform Capabilities
│   ├── config.py           # Pydantic BaseSettings loading .env
│   ├── database.py         # Async SQLAlchemy 2.0 Engine & AsyncSession
│   ├── redis.py            # Async Redis connection pool & caching client
│   ├── security.py         # Phone + PIN auth, JWT encode/decode, RBAC guards
│   ├── response.py         # Standardized API response envelope format
│   ├── celery_app.py       # Celery task queue & beat scheduler instance
│   └── models_registry.py  # Imports every ORM models.py once, for alembic/env.py and tasks.py
│
├── common/                 # 🛠️ Shared Utilities & Middlewares
│   ├── exceptions.py       # Global domain exception hierarchy & FastAPI handlers
│   └── middleware.py       # Request correlation ID & execution latency middleware
│
├── modules/                # 🧩 Vertical Domain Modules (Self-contained business units)
│   ├── auth/               # 🔑 Slice 1: Phone + 6-digit PIN login & JWT token exchange
│   │   ├── models.py       # ORM Models (User, RefreshToken)
│   │   ├── repository.py   # Statement-only DB access (no commit/rollback)
│   │   ├── router.py       # API Endpoints (/auth/login, /auth/change-password, /auth/refresh, /auth/logout)
│   │   ├── service.py      # Business Logic (PIN verification, token minting, first-login flag)
│   │   └── schemas.py      # Pydantic DTOs (LoginRequest, AuthTokenResponse, ...)
│   │
│   ├── admin/              # 🩺 Slice 2: Doctor account management & audit logs
│   │   ├── models.py       # (DoctorProfile, AuditLog)
│   │   ├── repository.py
│   │   ├── router.py
│   │   ├── service.py
│   │   └── schemas.py
│   │
│   ├── patients/           # 🧑‍⚕️ Slice 3 & 4: Patient profiles, routines & caregiver links
│   │   ├── models.py       # (PatientProfile, PatientRoutine, CaregiverLink)
│   │   ├── repository.py
│   │   ├── router.py
│   │   ├── service.py
│   │   └── schemas.py
│   │
│   ├── prescriptions/      # 💊 Slice 5: Medication directory & Prescriptions (Header/Item)
│   │   ├── models.py       # (Medication, Prescription, PrescriptionItem)
│   │   ├── repository.py
│   │   ├── router.py
│   │   ├── service.py
│   │   └── schemas.py
│   │
│   ├── agents/             # 🧠 Slice 6: Intake Scheduler & patient chat endpoints
│   │   ├── models.py       # (AgentRun, ScheduledDose)
│   │   ├── planner.py      # Deterministic dose expansion (pure functions, no DB/IO) — the real "tầng 1" solver
│   │   ├── grouping.py     # Groups ScheduleRow entries for notification batching
│   │   ├── repository.py
│   │   ├── router.py
│   │   ├── service.py      # SchedulingService + ChatService
│   │   ├── tasks.py        # Celery async tasks for deterministic schedule generation
│   │   └── schemas.py
│   │
│   ├── adherence/          # 📊 Slice 7: Intake logging, SOS alerts & Health surveys
│   │   ├── models.py       # (AdherenceLog, HealthSurvey, SymptomReport, Alert)
│   │   ├── repository.py
│   │   ├── router.py
│   │   ├── service.py
│   │   └── schemas.py
│   │
│   ├── dashboard/          # 📈 Slice 8: Doctor portal read models & live event feed
│   │   ├── repository.py   # Cross-slice read-only aggregates (no models.py: owns no table)
│   │   ├── router.py       # /dashboard/* plus the WS /ws/dashboard handler
│   │   ├── service.py
│   │   └── schemas.py
│   │
│   └── planning/           # 🧪 Shared clinical helpers for the agent layer
│       └── core/           # backend_client.py, llm.py, speech.py (only these 3 exist — no clinical.py/timekit.py/prescription_validator.py)
│
├── api/                    # 🌐 API Routing & Dependency Injection
│   ├── deps.py             # Global FastAPI dependencies (get_db, get_current_user, RBAC)
│   └── v1_router.py        # Single API v1 router combining all module sub-routers
│
└── main.py                 # 🚀 FastAPI App entrypoint, CORS & WebSocket Handlers
```

---

## 🏛 Architecture Patterns & Guidelines

### 1. Vertical Slice Domain Isolation
Each business module inside `src/modules/<domain>/` is self-contained. It encapsulates:
- `models.py`: SQLAlchemy 2.0 ORM models for that domain. Omit it when the module owns no table (`dashboard/` only reads other slices').
- `schemas.py`: Pydantic v2 Request/Response DTOs.
- `repository.py`: Statement-only DB access — `add`/`execute`/`flush`, never `commit`/`rollback`.
- `service.py`: Domain logic and transaction ownership (`async with self._db.begin():`).
- `router.py`: FastAPI endpoint handlers delegating to `service.py`.
- `tasks.py`: Celery async tasks specific to the domain.

Modules do not import each other's `service.py`. Sharing a repository across
slices is accepted where the access rule is genuinely the same data (several
services construct `PatientRepository`); anything else is duplicated on purpose
rather than creating a module-to-module edge. When two slices need to exchange
something at runtime — a write path notifying the dashboard, for example — the
channel belongs in `core/`, not in either module.

### 2. Core Infrastructure Layer (`src/core/`)
Single place for low-level technical infrastructure:
- `config.py`: Environment configuration via Pydantic `BaseSettings`.
- `database.py`: Async engine, sessionmaker, and Base ORM model.
- `security.py`: JWT signing/decoding, phone validation, RBAC dependencies, and actor-token propagation for in-process agent calls.
- `redis.py`: Async Redis connection pool, plus the dashboard event channel (publish/subscribe and its frame envelope).
- `response.py`: The standard API response envelope.
- `celery_app.py`: Main Celery application setup.
- `models_registry.py`: Imports every `src/modules/*/models.py` once, so a mapped class always registers on `Base.metadata` before `configure_mappers()` runs. `alembic/env.py` and every `src/modules/*/tasks.py` that touches the ORM import this module instead of hand-listing model modules — the same list duplicated across those files is what let `NoReferencedTableError` reach production undetected (`docs/adherence-review-fix-plan.md`).

### 3. API Router Aggregation (`src/api/`)
- `deps.py`: Shared dependencies (`get_db`, `get_current_user`, `require_roles`).
- `v1_router.py`: Combines all module routers under `/api/v1` namespace.

### 4. Mandatory API Response Envelope
All API endpoints MUST wrap JSON output in the standard envelope format:
```json
{
  "success": true,
  "code": 200,
  "message": "Operation description",
  "data": { ... },
  "errors": null
}
```
