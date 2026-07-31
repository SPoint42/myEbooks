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


def test_public_google_source_accepts_drive_folder_url(monkeypatch, tmp_path):
    monkeypatch.setenv("EBOOK_SOURCE", "google_public")
    monkeypatch.setenv("EBOOK_DATA_DIR", str(tmp_path))
    monkeypatch.setenv(
        "GOOGLE_DRIVE_PUBLIC_URL",
        "https://drive.google.com/drive/folders/1AbCdEfGhIjKlMnOpQrStUvWx",
    )

    settings = Settings.from_env()

    assert settings.source == "google_public"
    assert settings.google_drive_public_url.endswith("1AbCdEfGhIjKlMnOpQrStUvWx")


@pytest.mark.parametrize(
    "url",
    [
        "http://drive.google.com/drive/folders/1AbCdEfGhIjKlMnOpQrStUvWx",
        "https://evil.example/drive/folders/1AbCdEfGhIjKlMnOpQrStUvWx",
        "https://drive.google.com/file/d/1AbCdEfGhIjKlMnOpQrStUvWx/view",
    ],
)
def test_public_google_source_rejects_unsafe_or_non_folder_url(monkeypatch, url):
    monkeypatch.setenv("EBOOK_SOURCE", "google_public")
    monkeypatch.setenv("GOOGLE_DRIVE_PUBLIC_URL", url)

    with pytest.raises(ValueError, match="GOOGLE_DRIVE_PUBLIC_URL"):
        Settings.from_env()
