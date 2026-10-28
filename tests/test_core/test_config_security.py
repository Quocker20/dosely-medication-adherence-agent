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
