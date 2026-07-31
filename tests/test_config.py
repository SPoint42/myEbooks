from __future__ import annotations

import pytest

from myebooks.config import Settings


def test_settings_defaults_to_fake_source(monkeypatch, tmp_path):
    monkeypatch.delenv("EBOOK_SOURCE", raising=False)
    monkeypatch.setenv("EBOOK_DATA_DIR", str(tmp_path))

    settings = Settings.from_env()

    assert settings.source == "fake"
    assert settings.database_path == tmp_path / "myebooks.sqlite3"


def test_google_source_requires_credentials(monkeypatch, tmp_path):
    monkeypatch.setenv("EBOOK_SOURCE", "google")
    monkeypatch.setenv("EBOOK_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("GOOGLE_SERVICE_ACCOUNT_FILE", raising=False)

    with pytest.raises(ValueError, match="GOOGLE_SERVICE_ACCOUNT_FILE"):
        Settings.from_env()


def test_invalid_source_is_rejected(monkeypatch):
    monkeypatch.setenv("EBOOK_SOURCE", "dropbox")

    with pytest.raises(ValueError, match="EBOOK_SOURCE"):
        Settings.from_env()
