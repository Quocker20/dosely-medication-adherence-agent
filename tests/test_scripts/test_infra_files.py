"""Lightweight structural checks for deployment files (compose, Caddyfile, Docker)."""

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
COMPOSE = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
APP_SERVICES = ("backend", "worker", "beat")


def _env(service: dict) -> dict[str, str]:
    env = service.get("environment", [])
    if isinstance(env, dict):
        return {k: str(v) for k, v in env.items()}
    return dict(item.split("=", 1) for item in env)


def test_app_services_set_production_explicitly():
    for name in APP_SERVICES:
        assert _env(COMPOSE["services"][name]).get("APP_ENV") == "production", name
