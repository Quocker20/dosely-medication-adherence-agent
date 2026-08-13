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
    postgres_user: str
    postgres_password: str
    postgres_db: str
    postgres_host: str = "postgres"
    postgres_port: int = 5432
    database_url: str

    # Redis Cache & Message Broker
    redis_host: str = "redis"
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

    # LLM
    openai_api_key: str = ""
    model_name: str = "gpt-4o-mini"
    llm_temperature: float = Field(default=0.7, ge=0.0, le=2.0)

    # Speech (STT/TTS) — src/agents/services/speech.py
    stt_model: str = "whisper-1"
    tts_model: str = "tts-1"
    tts_voice: str = "alloy"

    # Backend HTTP client cho agent tools — src/agents/services/backend_client.py
    api_base_url: str = "http://localhost:8000/api/v1"
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
    planning_agent_timeout_ms: int = Field(default=15000, ge=1000, le=60000)
    # Slice 6: rolling generation window. Bounds scheduled_doses row count for
    # open-ended prescriptions (nullable end_date) — a Beat job tops this up
    # daily rather than generating the whole treatment course up front.
    schedule_horizon_days: int = Field(default=14, ge=1, le=90)
    doctor_id: str = "dr-nguyen-van-a"
    doctor_name: str = "BS. Nguyễn Văn A"
    doctor_specialty: str = "Nội tim mạch"


@lru_cache
def get_settings() -> Settings:
    return Settings()
