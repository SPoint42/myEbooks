from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _positive_int(name: str, default: int) -> int:
    raw = os.getenv(name, str(default))
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} doit être un entier") from exc
    if value <= 0:
        raise ValueError(f"{name} doit être strictement positif")
    return value


@dataclass(frozen=True, slots=True)
class Settings:
    data_dir: Path
    source: str = "fake"
    google_service_account_file: Path | None = None
    google_drive_id: str | None = None
    google_drive_folder_id: str | None = None
    max_file_size: int = 150 * 1024 * 1024
    max_epub_expanded_size: int = 300 * 1024 * 1024
    max_epub_entries: int = 10_000

    @property
    def database_path(self) -> Path:
        return self.data_dir / "myebooks.sqlite3"

    @property
    def covers_dir(self) -> Path:
        return self.data_dir / "covers"

    @classmethod
    def from_env(cls) -> Settings:
        source = os.getenv("EBOOK_SOURCE", "fake").strip().lower()
        if source not in {"fake", "google"}:
            raise ValueError("EBOOK_SOURCE doit valoir 'fake' ou 'google'")

        credentials = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE")
        settings = cls(
            data_dir=Path(os.getenv("EBOOK_DATA_DIR", "data")).expanduser().resolve(),
            source=source,
            google_service_account_file=(
                Path(credentials).expanduser().resolve() if credentials else None
            ),
            google_drive_id=os.getenv("GOOGLE_DRIVE_ID") or None,
            google_drive_folder_id=os.getenv("GOOGLE_DRIVE_FOLDER_ID") or None,
            max_file_size=_positive_int("EBOOK_MAX_FILE_SIZE", 150 * 1024 * 1024),
            max_epub_expanded_size=_positive_int(
                "EBOOK_MAX_EPUB_EXPANDED_SIZE", 300 * 1024 * 1024
            ),
            max_epub_entries=_positive_int("EBOOK_MAX_EPUB_ENTRIES", 10_000),
        )
        settings.validate()
        return settings

    def validate(self) -> None:
        if self.source != "google":
            return
        if not self.google_service_account_file:
            raise ValueError("GOOGLE_SERVICE_ACCOUNT_FILE est requis avec EBOOK_SOURCE=google")
        if not self.google_service_account_file.is_file():
            raise ValueError("GOOGLE_SERVICE_ACCOUNT_FILE ne pointe pas vers un fichier lisible")
        if not (self.google_drive_id or self.google_drive_folder_id):
            raise ValueError("GOOGLE_DRIVE_ID ou GOOGLE_DRIVE_FOLDER_ID est requis")
