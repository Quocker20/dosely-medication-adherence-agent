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

    # App
    app_name: str = "AI20K Agent"
    app_env: Literal["development", "production", "test"] = "development"
    app_port: int = Field(default=8000, ge=1, le=65535)
    app_host: str = "0.0.0.0"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    cors_origins: str = "http://localhost:5173,http://localhost:3000"

    # LLM
    openai_api_key: str = ""
    model_name: str = "gpt-4o-mini"
    llm_temperature: float = Field(default=0.7, ge=0.0, le=2.0)

    # Database
    database_url: str = "sqlite:///./data/app.db"

    # Vector Store
    chroma_persist_dir: str = "./data/chroma"

    # RemindRx — luật lâm sàng chạy bằng code xác định (không phải LLM).
    # Xem docs/RemindRx_Tong_Hop_Tai_Lieu.md mục 7.2 "Guardrails bắt buộc".
    max_frequency_per_day: int = Field(default=4, ge=1, le=12)
    max_treatment_days: int = Field(default=180, ge=1, le=3650)
    min_dose_gap_minutes: int = Field(default=240, ge=0, le=1440)
    # D-01 chưa chốt (Brief "> 3" vs PRD "3") — baseline theo PRD, đổi bằng env.
    missed_dose_alert_threshold: int = Field(default=3, ge=1, le=10)
    planning_agent_timeout_ms: int = Field(default=15000, ge=1000, le=60000)
    doctor_id: str = "dr-nguyen-van-a"
    doctor_name: str = "BS. Nguyễn Văn A"
    doctor_specialty: str = "Nội tim mạch"


@lru_cache
def get_settings() -> Settings:
    return Settings()
