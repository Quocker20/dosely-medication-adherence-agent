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


def test_caddyfile_has_security_headers_and_body_limit():
    text = (ROOT / "Caddyfile").read_text(encoding="utf-8")
    assert "Strict-Transport-Security" in text
    assert 'X-Content-Type-Options "nosniff"' in text
    assert 'X-Frame-Options "DENY"' in text
    assert 'Referrer-Policy "strict-origin-when-cross-origin"' in text
    assert "request_body" in text

    import re

    from src.core.config import Settings

    match = re.search(r"max_size\s+(\d+)MB", text)
    assert match, "request_body max_size must be set in MB"
    voice_limit = Settings.model_fields["voice_max_upload_bytes"].default
    assert int(match.group(1)) * 1024 * 1024 >= voice_limit + 64 * 1024
