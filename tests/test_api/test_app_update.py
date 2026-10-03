from urllib.parse import urlparse

from fastapi.testclient import TestClient

from src.core.config import get_settings
from src.main import app


def test_latest_app_version_is_public_and_uses_settings(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "android_latest_version_code", 7)
    monkeypatch.setattr(settings, "android_latest_version_name", "1.5.0")
    monkeypatch.setattr(settings, "android_latest_apk_filename", "dosely-demo.apk")

    response = TestClient(app).get("/api/v1/app/latest-version")

    assert response.status_code == 200
    payload = response.json()
    assert payload == {
        "success": True,
        "code": 200,
        "message": "Latest Android version fetched successfully",
        "data": {
            "versionCode": 7,
            "versionName": "1.5.0",
            "downloadUrl": "http://testserver/downloads/dosely-demo.apk",
        },
        "errors": None,
    }

    assert urlparse(payload["data"]["downloadUrl"]).path == "/downloads/dosely-demo.apk"
