from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # App Config
    app_name: str = "ADHE REMIND API"
    app_env: Literal["development", "production", "test"] = "development"
    app_port: int = Field(default=8000, ge=1, le=65535)
    app_host: str = "0.0.0.0"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    cors_origins: str = "http://localhost:3000,http://localhost:5173"

    # PostgreSQL Database
    # Defaults are the host-side view (pytest/alembic/uvicorn run on the
    # developer's machine); docker-compose overrides them with the in-network
    # hostnames for the backend and worker containers.
    postgres_user: str
    postgres_password: str
    postgres_db: str
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    database_url: str

    # Redis Cache & Message Broker
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_url: str

    # Read-through response cache (src/core/cache.py). Keyed under
    # cache_key_prefix so it never collides with DASHBOARD_EVENTS_CHANNEL or
    # any future Redis use on the same instance.
    cache_enabled: bool = True
    cache_key_prefix: str = "remindrx:cache"
    # Medication catalog: no PHI, admin-seeded, changes rarely.
    cache_ttl_medications_seconds: int = Field(default=3600, ge=0, le=86400)
    # Doctor dashboard aggregates: WS /ws/dashboard pushes deltas, so a short
    # TTL is enough to absorb roster/detail read load without the portal
    # looking stale between events.
    cache_ttl_dashboard_seconds: int = Field(default=45, ge=0, le=3600)
    # Adherence summary for a range that still includes today (counts can
    # still change).
    cache_ttl_adherence_current_seconds: int = Field(default=60, ge=0, le=3600)
    # Adherence summary for a range that ended before today — the underlying
    # logs are append-only and the range is closed, so this is immutable.
    cache_ttl_adherence_historical_seconds: int = Field(default=86400, ge=0, le=604800)

    # Celery Task Queue
    celery_broker_url: str
    celery_result_backend: str

    # JWT Security
    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7

    # Firebase
    firebase_service_account_key_path: str = "firebase-adminsdk.json"

    # LLM
    openai_api_key: str = ""
    openai_base_url: str | None = None
    model_name: str = "gpt-4o-mini"
    llm_temperature: float = Field(default=0.7, ge=0.0, le=2.0)

    # Speech (STT/TTS) — src/modules/planning/core/speech.py
    stt_model: str = "whisper-1"
    tts_model: str = "tts-1"
    tts_voice: str = "alloy"

    # Backend HTTP client cho agent tools — src/modules/planning/core/backend_client.py
    api_base_url: str = "http://localhost:8000/api/v1"
    # Fallback identity chỉ dùng ngoài request (worker nền). Trong luồng chat,
    # backend_client ưu tiên token của chính người gọi — xem src/core/security.py.
    api_service_token: str = ""
    api_timeout_seconds: int = 10

    # Password Security
    password_pepper: str

    # RemindRx — luật lâm sàng chạy bằng code xác định (không phải LLM).
    # Xem docs/RemindRx_Tong_Hop_Tai_Lieu.md mục 7.2 "Guardrails bắt buộc".
    max_frequency_per_day: int = Field(default=4, ge=1, le=12)
    max_treatment_days: int = Field(default=180, ge=1, le=3650)
    # Chỉ là fallback khi PrescriptionItem.minimum_interval_minutes để NULL —
    # tức bác sĩ cố ý không đặt ràng buộc giãn cách cho thuốc đó. Mặc định 0
    # (không ép giãn cách): đặt sàn 4h như trước làm lịch ăn sáng/ăn trưa kiểu
    # VN (7h/11h) vi phạm ngay và agent không sinh được lịch. Muốn dựng lại sàn
    # an toàn toàn hệ thống thì set MIN_DOSE_GAP_MINUTES trong env.
    min_dose_gap_minutes: int = Field(default=0, ge=0, le=1440)
    # D-01 chưa chốt (Brief "> 3" vs PRD "3") — baseline theo PRD, đổi bằng env.
    missed_dose_alert_threshold: int = Field(default=3, ge=1, le=10)
    # Missed-dose scan job (Celery Beat) — see prbm.md #1 / planner.py trigger 1.
    missed_dose_overdue_minutes: int = Field(default=60, ge=1, le=1440)
    missed_dose_scan_interval_minutes: int = Field(default=15, ge=1, le=1440)
    planning_agent_timeout_ms: int = Field(default=15000, ge=1000, le=60000)
    planning_run_lease_seconds: int = Field(default=180, ge=60, le=900)
    planning_grouping_enabled: bool = False
    rate_limit_enabled: bool = True
    # Duyệt đơn xong thì Planning Agent tự sinh lịch (docs mục 8: approve phát
    # event PrescriptionApproved). Tắt cờ này thì bác sĩ phải gọi tay
    # POST /patients/{id}/schedules/generate như trước.
    prescription_autoschedule_enabled: bool = True
    # uq_agent_runs_one_running chỉ cho một run/bệnh nhân. Duyệt hai đơn liên
    # tiếp thì đơn sau phải đợi — retry cho tới khi run trước xong, vì bỏ qua
    # đồng nghĩa bệnh nhân không có lịch nhắc cho thuốc vừa được kê.
    prescription_autoschedule_retry_seconds: int = Field(default=30, ge=5, le=600)
    prescription_autoschedule_max_retries: int = Field(default=10, ge=1, le=60)
    notification_group_window_minutes: int = Field(default=30, ge=0, le=180)
    # Slice 6: rolling generation window. Bounds scheduled_doses row count for
    # open-ended prescriptions (nullable end_date) — a Beat job tops this up
    # daily rather than generating the whole treatment course up front.
    schedule_horizon_days: int = Field(default=14, ge=1, le=90)
    # Slice 8: how far back the doctor dashboard looks when computing the
    # headline adherence rate. A rolling window from "now", not calendar days,
    # so one shared bound serves every patient regardless of their timezone.
    dashboard_adherence_window_days: int = Field(default=7, ge=1, le=90)
    dashboard_recent_alerts_limit: int = Field(default=5, ge=1, le=50)
    # Nightly graded-adherence review (docs/graded-adherence-implementation.md
    # Stage 3+). A closed calendar window [D-window_days, D) in
    # adherence_review_timezone, not a rolling "now - N days" — the escalation
    # ladder compares night-over-night, so each night's window must be fixed
    # once computed rather than drifting as the day progresses.
    adherence_review_window_days: int = Field(default=7, ge=1, le=90)
    # Single deployment-wide timezone for the nightly window boundary, not
    # per-patient: per-patient boundaries would force one query per patient,
    # which is exactly the N+1 this stage's indicator queries exist to avoid.
    # Matches patient_profiles.timezone's own default and Celery's configured
    # timezone. Revisit only if the platform ships outside one timezone.
    adherence_review_timezone: str = "Asia/Ho_Chi_Minh"
    # A patient with fewer doses than this in the window has no meaningful
    # rate to judge — same reasoning as the zero-dose dashboard-band fix on
    # this branch (dashboard/repository.py adherence_band filters).
    adherence_review_min_doses: int = Field(default=5, ge=1, le=100)
    # Severity bands, aligned with the doctor dashboard's existing 50/70
    # adherence_band cutoffs (dashboard/repository.py) so the same percentage
    # reads the same tier on both screens. adherence_mild_threshold is the
    # all-clear line: at or above it, severity is NONE.
    adherence_severe_threshold: float = Field(default=50.0, ge=0, le=100)
    adherence_moderate_threshold: float = Field(default=70.0, ge=0, le=100)
    adherence_mild_threshold: float = Field(default=80.0, ge=0, le=100)
    # Week-over-week drop (current_rate - prior_rate, so this is negative)
    # at or below which severity is bumped one level regardless of the band
    # it already landed in — a fast deterioration matters even inside an
    # otherwise-tolerable band.
    adherence_trend_alarm_delta: float = Field(default=-20.0, ge=-100, le=0)
    # Escalation-ladder day breakpoints (docs/graded-adherence-implementation.md
    # Stage 4.2): three typed ints rather than one parsed CSV string, so
    # Pydantic validates them at startup instead of a bad string surfacing as
    # a runtime crash mid-scan. day5 has no upper bound in the ladder itself
    # ("day 5+") — it is the day this and every later day shares one column.
    adherence_review_escalation_day1: int = Field(default=1, ge=1, le=365)
    adherence_review_escalation_day3: int = Field(default=3, ge=1, le=365)
    adherence_review_escalation_day5: int = Field(default=5, ge=1, le=365)
    # Doctor-facing re-notification cadence once an alert/warning starts
    # firing for a patient stuck at one severity — without this, a patient
    # at SEVERE for 30 nights pages the doctor 30 times. A FRESH escalation
    # (severity just rose, or just entered this action tier) always fires
    # regardless of cooldown; see AdherenceEscalationService for the exact
    # "days since this action tier started" rule.
    adherence_review_cooldown_days: int = Field(default=3, ge=1, le=30)
    # Patient-facing notifications are throttled separately and more
    # gently — a daily nudge while MILD is tolerable in a way a daily
    # doctor page is not.
    adherence_review_patient_cooldown_days: int = Field(default=1, ge=1, le=30)
    doctor_id: str = "dr-nguyen-van-a"
    doctor_name: str = "BS. Nguyễn Văn A"
    doctor_specialty: str = "Nội tim mạch"


@lru_cache
def get_settings() -> Settings:
    return Settings()
