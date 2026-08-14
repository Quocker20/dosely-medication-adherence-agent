# ADHE REMIND — Backend Architecture & Project Structure Guide

This document defines the modular domain-driven architecture for the **ADHE REMIND** medication adherence platform backend.

---

## 📁 System Directory Tree

```
src/
├── agents/                 # 🧠 LangGraph Agent
│   ├── graph.py            # State graph (nodes + edges)
│   ├── state.py            # State schema (TypedDict)
│   ├── nodes/              # Node functions
│   └── tools/              # Agent tools (@tool)
│
├── core/                   # ⚙️ Infrastructure & Shared Platform Capabilities
│   ├── config.py           # Pydantic BaseSettings loading .env
│   ├── database.py         # Async SQLAlchemy 2.0 Engine & AsyncSession
│   ├── redis.py            # Async Redis connection pool & caching client
│   ├── security.py         # Phone + OTP auth, JWT encode/decode, RBAC guards
│   ├── response.py         # Standardized API response envelope format
│   └── celery_app.py       # Celery task queue & beat scheduler instance
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
│   │   ├── planner.py      # Deterministic dose expansion (pure functions, no DB/IO)
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
│       └── core/           # backend_client, clinical, llm, speech, timekit, prescription_validator
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
