import hashlib
import os

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from src.core.config import Settings, get_settings
from src.main import app
from src.modules.app_update import service as update_service

BASE = "https://downloads.example.test"


@pytest.fixture
def apk_dir(tmp_path, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "android_latest_version_code", 7)
    monkeypatch.setattr(settings, "android_latest_version_name", "1.5.0")
    monkeypatch.setattr(settings, "android_latest_apk_filename", "dosely-demo.apk")
    monkeypatch.setattr(settings, "android_download_base_url", BASE)
    monkeypatch.setattr(update_service, "DOWNLOADS_DIR", tmp_path)
    update_service._sha256_cache.clear()
    return tmp_path


def _get(headers=None):
    return TestClient(app).get("/api/v1/app/latest-version", headers=headers)


def test_latest_app_version_returns_sha256_and_configured_https_url(apk_dir):
    content = b"fake-apk-bytes" * 1000
    (apk_dir / "dosely-demo.apk").write_bytes(content)

    response = _get()

    assert response.status_code == 200
    assert response.json() == {
        "success": True,
        "code": 200,
        "message": "Latest Android version fetched successfully",
        "data": {
            "versionCode": 7,
            "versionName": "1.5.0",
            "downloadUrl": f"{BASE}/downloads/dosely-demo.apk",
            "sha256": hashlib.sha256(content).hexdigest(),
        },
        "errors": None,
    }


def test_download_url_ignores_request_host_header(apk_dir):
    (apk_dir / "dosely-demo.apk").write_bytes(b"x")
    data = _get(headers={"Host": "evil.example", "X-Forwarded-Host": "evil.example"}).json()["data"]
    assert data["downloadUrl"].startswith(BASE + "/")


def test_sha256_is_cached_by_mtime(apk_dir, monkeypatch):
    apk = apk_dir / "dosely-demo.apk"
    apk.write_bytes(b"one")
    calls = []
    real = update_service._hash_file

    def counting(path):
        calls.append(path)
        return real(path)

    monkeypatch.setattr(update_service, "_hash_file", counting)

    first = _get().json()["data"]["sha256"]
    second = _get().json()["data"]["sha256"]
    assert first == second == hashlib.sha256(b"one").hexdigest()
    assert len(calls) == 1

    apk.write_bytes(b"two!")
    stat = apk.stat()
    os.utime(apk, ns=(stat.st_atime_ns, stat.st_mtime_ns + 5_000_000_000))
    third = _get().json()["data"]["sha256"]
    assert third == hashlib.sha256(b"two!").hexdigest()
    assert len(calls) == 2


def test_missing_apk_yields_null_sha256(apk_dir):
    data = _get().json()["data"]
    assert data["sha256"] is None
    assert data["downloadUrl"] == f"{BASE}/downloads/dosely-demo.apk"


def test_download_base_url_must_be_https_and_is_normalised():
    data = get_settings().model_dump()
    data["android_download_base_url"] = "http://insecure.example"
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **data)
    data["android_download_base_url"] = "https://ok.example/"
    assert Settings(_env_file=None, **data).android_download_base_url == "https://ok.example"
