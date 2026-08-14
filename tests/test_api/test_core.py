import pytest
from fastapi.testclient import TestClient

from src.core.config import get_settings
from src.core.response import error_response, success_response
from src.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    validate_phone_number,
)
from src.common.exceptions import ValidationException
from src.main import app


def test_settings_load():
    settings = get_settings()
    assert settings.app_name == "ADHE REMIND API"
    assert settings.jwt_algorithm == "HS256"
    # Deliberately no assertion on postgres_host/redis_host: those differ
    # between a host-side run and a container, and nothing in the code reads
    # them anyway — database_url/redis_url carry the real connection.
    assert settings.database_url
    assert settings.redis_url


def test_phone_validation():
    assert validate_phone_number("0912345678") == "+84912345678"
    assert validate_phone_number("+84912345678") == "+84912345678"
    assert validate_phone_number("84912345678") == "+84912345678"
    
    with pytest.raises(ValidationException):
        validate_phone_number("12345")


def test_jwt_tokens_phone_otp():
    token = create_access_token(user_id="usr_01", role="DOCTOR", phone_number="+84912345678")
    payload = decode_token(token)
    assert payload["sub"] == "usr_01"
    assert payload["role"] == "DOCTOR"
    assert payload["phone_number"] == "+84912345678"
    assert payload["type"] == "access"

    refresh = create_refresh_token(user_id="usr_01")
    refresh_payload = decode_token(refresh)
    assert refresh_payload["sub"] == "usr_01"
    assert refresh_payload["type"] == "refresh"


def test_health_endpoint():
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_response_envelope():
    succ = success_response(data={"key": "val"}, message="Operation succeeded")
    assert succ.status_code == 200
    
    err = error_response(message="Bad request", code=400, errors={"field": "invalid"})
    assert err.status_code == 400
