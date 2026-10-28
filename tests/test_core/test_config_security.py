"""SEC-06 / SEC-13 / SEC-14: settings validation for secrets, CORS and echo."""

import pytest
from pydantic import ValidationError

from src.core.config import Settings, get_settings


def _build(**overrides) -> Settings:
    data = get_settings().model_dump()
    data.update(overrides)
    return Settings(_env_file=None, **data)


def test_jwt_secret_too_short_rejected():
    with pytest.raises(ValidationError):
        _build(jwt_secret_key="short")


def test_password_pepper_too_short_rejected():
    with pytest.raises(ValidationError):
        _build(password_pepper="x" * 31)


def test_secrets_of_32_chars_accepted():
    s = _build(jwt_secret_key="a" * 32, password_pepper="b" * 32)
    assert len(s.jwt_secret_key) == 32


def test_sql_echo_defaults_off_and_independent_of_env():
    assert _build(app_env="development").sql_echo is False
    assert _build(sql_echo=True, app_env="production", cors_origins="https://a.example").sql_echo is True


def test_app_env_default_unchanged():
    assert Settings.model_fields["app_env"].default == "development"


# --- SEC-13: CORS ----------------------------------------------------------


def test_cors_origins_are_stripped_and_blanks_dropped():
    s = _build(cors_origins=" https://a.example , ,https://b.example ,")
    assert s.cors_origin_list == ["https://a.example", "https://b.example"]


def test_production_rejects_empty_cors_origins():
    with pytest.raises(ValidationError):
        _build(app_env="production", cors_origins=" , ")


def test_production_accepts_explicit_origins():
    s = _build(app_env="production", cors_origins="https://dosely.example")
    assert s.cors_origin_list == ["https://dosely.example"]


def test_non_production_may_have_empty_cors_origins():
    assert _build(app_env="development", cors_origins="").cors_origin_list == []


# --- SEC-13 / SEC-14: app factory -----------------------------------------


def test_production_app_disables_docs_and_openapi():
    from src.main import create_app

    app = create_app(_build(app_env="production", cors_origins="https://dosely.example"))
    assert app.docs_url is None
    assert app.redoc_url is None
    assert app.openapi_url is None


def test_non_production_app_keeps_docs():
    from src.main import create_app

    app = create_app(_build(app_env="development"))
    assert app.docs_url == "/docs"
    assert app.openapi_url == "/openapi.json"


def test_cors_preflight_is_explicit_not_wildcard():
    from fastapi.testclient import TestClient

    from src.main import create_app

    client = TestClient(create_app(_build(app_env="production", cors_origins="https://dosely.example")))
    ok = client.options(
        "/health",
        headers={
            "Origin": "https://dosely.example",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )
    assert ok.headers["access-control-allow-origin"] == "https://dosely.example"
    assert ok.headers["access-control-allow-methods"] != "*"
    assert "TRACE" not in ok.headers["access-control-allow-methods"]
    bad = client.options(
        "/health",
        headers={
            "Origin": "https://evil.example",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert "access-control-allow-origin" not in bad.headers
    bad_header = client.options(
        "/health",
        headers={
            "Origin": "https://dosely.example",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "x-custom-evil",
        },
    )
    assert bad_header.status_code == 400


def test_health_does_not_expose_env():
    from fastapi.testclient import TestClient

    from src.main import app

    body = TestClient(app).get("/health").json()
    assert body == {"status": "ok"}
