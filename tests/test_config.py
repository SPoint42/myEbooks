from __future__ import annotations

import pytest

from myebooks.config import Settings, parse_index_extensions


def test_settings_defaults_to_fake_source(monkeypatch, tmp_path):
    monkeypatch.delenv("EBOOK_SOURCE", raising=False)
    monkeypatch.setenv("EBOOK_DATA_DIR", str(tmp_path))

    settings = Settings.from_env()

    assert settings.source == "fake"
    assert settings.database_path == tmp_path / "myebooks.sqlite3"
    assert settings.background_index is False
    assert settings.index_extensions == frozenset({"epub"})


def test_index_extensions_are_normalized_from_environment(monkeypatch, tmp_path):
    monkeypatch.setenv("EBOOK_SOURCE", "fake")
    monkeypatch.setenv("EBOOK_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("EBOOK_INDEX_EXTENSIONS", ".EPUB, pdf")

    settings = Settings.from_env()

    assert settings.index_extensions == frozenset({"epub", "pdf"})


@pytest.mark.parametrize("raw", ["", "epub,,pdf", "mobi", "epub,exe"])
def test_unsupported_or_empty_index_extensions_are_rejected(raw):
    with pytest.raises(ValueError):
        parse_index_extensions(raw)


def test_background_index_settings_are_parsed(monkeypatch, tmp_path):
    monkeypatch.setenv("EBOOK_SOURCE", "fake")
    monkeypatch.setenv("EBOOK_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("EBOOK_BACKGROUND_INDEX", "true")
    monkeypatch.setenv("EBOOK_FORCE_INDEX_ON_START", "1")

    settings = Settings.from_env()

    assert settings.background_index is True
    assert settings.force_index_on_start is True


def test_invalid_background_index_setting_is_rejected(monkeypatch):
    monkeypatch.setenv("EBOOK_BACKGROUND_INDEX", "sometimes")

    with pytest.raises(ValueError, match="EBOOK_BACKGROUND_INDEX"):
        Settings.from_env()


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
        "https://drive.google.com/drive/folders/1AbCdEfGhIjKlMnOpQrStUvWx?usp=sharing",
    )

    settings = Settings.from_env()

    assert settings.source == "google_public"
    assert settings.google_drive_public_url.endswith("1AbCdEfGhIjKlMnOpQrStUvWx?usp=sharing")


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


def test_local_source_accepts_existing_directory(monkeypatch, tmp_path):
    library = tmp_path / "ebooks"
    library.mkdir()
    monkeypatch.setenv("EBOOK_SOURCE", "local")
    monkeypatch.setenv("EBOOK_LOCAL_DIR", str(library))

    settings = Settings.from_env()

    assert settings.source == "local"
    assert settings.local_library_dir == library


def test_local_source_requires_existing_directory(monkeypatch, tmp_path):
    monkeypatch.setenv("EBOOK_SOURCE", "local")
    monkeypatch.setenv("EBOOK_LOCAL_DIR", str(tmp_path / "missing"))

    with pytest.raises(ValueError, match="EBOOK_LOCAL_DIR"):
        Settings.from_env()
