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


def test_redis_requires_password_and_is_not_published():
    redis = COMPOSE["services"]["redis"]
    assert "requirepass" in " ".join(redis["command"]) if isinstance(redis["command"], list) else "requirepass" in redis["command"]
    assert "ports" not in redis, "Redis must not be published to the host"
    assert "-a" in redis["healthcheck"]["test"][-1].split()
    assert "REDIS_PASSWORD" in " ".join(redis.get("environment", []))


def test_every_redis_url_in_compose_carries_the_password():
    for name in APP_SERVICES:
        env = _env(COMPOSE["services"][name])
        for key in ("REDIS_URL", "CELERY_BROKER_URL", "CELERY_RESULT_BACKEND"):
            assert env[key].startswith("redis://:${REDIS_PASSWORD"), (name, key)


def _dockerignore_lines() -> set[str]:
    return {
        line.strip()
        for line in (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    }


def test_dockerignore_excludes_secrets_and_non_runtime_trees():
    lines = _dockerignore_lines()
    for required in ("firebase-adminsdk.json", "downloads/", "android/", "tests/", "docs/", ".venv", ".env.*"):
        assert required in lines, required
    # The production RAG index must stay in the image.
    assert "!data/rag_dense_index_q1_q2/" in lines
    assert "!.env.example" not in lines


def test_dockerfile_runs_multiple_workers_configurable_via_env():
    text = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "--workers" in text
    assert "UVICORN_WORKERS" in text
    # SEC-04: proxy headers trusted only from the configured proxy network.
    assert "--proxy-headers" in text
    assert "--forwarded-allow-ips ${FORWARDED_ALLOW_IPS" in text
    assert "ENV FORWARDED_ALLOW_IPS=" in text
    assert "--forwarded-allow-ips *" not in text


def test_migrate_service_runs_alembic_and_gates_app_services():
    services = COMPOSE["services"]
    migrate = services["migrate"]
    assert "alembic upgrade head" in " ".join(migrate["command"]) if isinstance(migrate["command"], list) else "alembic upgrade head" in migrate["command"]
    assert migrate.get("restart", "no") == "no"
    assert _env(migrate).get("APP_ENV") == "production"
    for name in APP_SERVICES:
        dep = services[name]["depends_on"]["migrate"]
        assert dep["condition"] == "service_completed_successfully", name


def _requirement_names(path: str) -> set[str]:
    import re

    names = set()
    for raw in (ROOT / path).read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or line.startswith("-"):
            continue
        names.add(re.split(r"[\[<>=!~ ;]", line, maxsplit=1)[0].lower().replace("_", "-"))
    return names


def test_requirements_are_fully_pinned_and_runtime_only():
    for raw in (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if line:
            assert "==" in line and ">=" not in line, line
    runtime = _requirement_names("requirements.txt")
    for dev_only in ("pytest", "pytest-asyncio", "pytest-timeout", "ruff", "pypdf"):
        assert dev_only not in runtime, dev_only


def test_dev_requirements_extend_runtime_and_pin_tooling():
    text = (ROOT / "requirements-dev.txt").read_text(encoding="utf-8")
    assert "-r requirements.txt" in text
    dev = _requirement_names("requirements-dev.txt")
    for tool in ("pytest", "pytest-asyncio", "pytest-timeout", "ruff", "pypdf", "mypy"):
        assert tool in dev, tool


def test_direct_requirements_are_all_resolved_in_lockfile():
    assert _requirement_names("requirements.in") <= _requirement_names("requirements.txt")


def test_pyproject_dependencies_match_requirements_in():
    import tomllib

    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    declared = {d.split("[")[0].split(">")[0].split("=")[0].strip().lower().replace("_", "-") for d in data["project"]["dependencies"]}
    assert declared == _requirement_names("requirements.in")
    extras = {d.lower().replace("_", "-") for d in data["project"]["optional-dependencies"]["dev"]}
    assert {"pytest", "pytest-asyncio", "pytest-timeout", "ruff", "pypdf", "mypy"} <= extras


def test_dockerfile_installs_only_runtime_requirements_and_ci_installs_dev():
    docker = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "requirements.txt" in docker and "requirements-dev" not in docker
    assert "requirements-dev.txt" in (ROOT / ".dockerignore").read_text(encoding="utf-8")
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "pip install -r requirements.txt" not in ci
    assert "requirements-dev.txt" in ci
