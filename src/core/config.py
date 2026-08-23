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
    min_dose_gap_minutes: int = Field(default=240, ge=0, le=1440)
    # D-01 chưa chốt (Brief "> 3" vs PRD "3") — baseline theo PRD, đổi bằng env.
    missed_dose_alert_threshold: int = Field(default=3, ge=1, le=10)
    # Missed-dose scan job (Celery Beat) — see prbm.md #1 / planner.py trigger 1.
    missed_dose_overdue_minutes: int = Field(default=60, ge=1, le=1440)
    missed_dose_scan_interval_minutes: int = Field(default=15, ge=1, le=1440)
    planning_agent_timeout_ms: int = Field(default=15000, ge=1000, le=60000)
    planning_run_lease_seconds: int = Field(default=180, ge=60, le=900)
    planning_grouping_enabled: bool = False
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
    doctor_id: str = "dr-nguyen-van-a"
    doctor_name: str = "BS. Nguyễn Văn A"
    doctor_specialty: str = "Nội tim mạch"


@lru_cache
def get_settings() -> Settings:
    return Settings()
