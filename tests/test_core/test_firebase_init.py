"""The app must boot without FCM credentials (local docker, CI, worktrees)."""

from unittest.mock import patch

from src.core import firebase_app
from src.core.config import get_settings


def test_init_firebase_without_key_file_warns_and_continues(monkeypatch, tmp_path, caplog):
    monkeypatch.setattr(get_settings(), "firebase_service_account_key_path", str(tmp_path / "missing.json"))

    with patch.object(firebase_app.firebase_admin, "initialize_app") as init_app:
        firebase_app.init_firebase()

    init_app.assert_not_called()
    assert "not found" in caplog.text


def test_init_firebase_with_unusable_key_file_does_not_raise(monkeypatch, tmp_path):
    """An empty file (e.g. what a missing docker bind-mount source becomes)."""
    bad = tmp_path / "firebase-adminsdk.json"
    bad.write_text("")
    monkeypatch.setattr(get_settings(), "firebase_service_account_key_path", str(bad))

    firebase_app.init_firebase()


def test_init_firebase_with_directory_as_key_path_does_not_raise(monkeypatch, tmp_path):
    """Docker creates a directory when a bind-mount source file is absent."""
    monkeypatch.setattr(get_settings(), "firebase_service_account_key_path", str(tmp_path))

    firebase_app.init_firebase()
