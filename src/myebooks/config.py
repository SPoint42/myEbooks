from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from .domain import SUPPORTED_EBOOK_EXTENSIONS

GOOGLE_DRIVE_FOLDER_PATH = re.compile(r"^/drive/folders/[A-Za-z0-9_-]{20,}/?$")


def _positive_int(name: str, default: int) -> int:
    raw = os.getenv(name, str(default))
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} doit être un entier") from exc
    if value <= 0:
        raise ValueError(f"{name} doit être strictement positif")
    return value


def _boolean(name: str, default: bool = False) -> bool:
    raw = os.getenv(name, "1" if default else "0").strip().lower()
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} doit être un booléen")


def parse_index_extensions(raw: str) -> frozenset[str]:
    parts = raw.split(",")
    extensions = frozenset(part.strip().lower().removeprefix(".") for part in parts)
    if not extensions or "" in extensions:
        raise ValueError("La liste d'extensions ne doit pas être vide")
    unsupported = extensions - SUPPORTED_EBOOK_EXTENSIONS
    if unsupported:
        raise ValueError(
            "Extension(s) non prise(s) en charge : "
            + ", ".join(sorted(unsupported))
            + ". Valeurs autorisées : epub, pdf."
        )
    return extensions


@dataclass(frozen=True, slots=True)
class Settings:
    data_dir: Path
    source: str = "fake"
    google_service_account_file: Path | None = None
    google_drive_id: str | None = None
    google_drive_folder_id: str | None = None
    google_drive_public_url: str | None = None
    local_library_dir: Path | None = None
    background_index: bool = False
    force_index_on_start: bool = False
    index_extensions: frozenset[str] = frozenset({"epub"})
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
        if source not in {"fake", "google", "google_public", "local"}:
            raise ValueError(
                "EBOOK_SOURCE doit valoir 'fake', 'google', 'google_public' ou 'local'"
            )

        credentials = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE")
        local_library = os.getenv("EBOOK_LOCAL_DIR")
        settings = cls(
            data_dir=Path(os.getenv("EBOOK_DATA_DIR", "data")).expanduser().resolve(),
            source=source,
            google_service_account_file=(
                Path(credentials).expanduser().resolve() if credentials else None
            ),
            google_drive_id=os.getenv("GOOGLE_DRIVE_ID") or None,
            google_drive_folder_id=os.getenv("GOOGLE_DRIVE_FOLDER_ID") or None,
            google_drive_public_url=os.getenv("GOOGLE_DRIVE_PUBLIC_URL") or None,
            local_library_dir=(
                Path(local_library).expanduser().resolve() if local_library else None
            ),
            background_index=_boolean("EBOOK_BACKGROUND_INDEX"),
            force_index_on_start=_boolean("EBOOK_FORCE_INDEX_ON_START"),
            index_extensions=parse_index_extensions(
                os.getenv("EBOOK_INDEX_EXTENSIONS", "epub")
            ),
            max_file_size=_positive_int("EBOOK_MAX_FILE_SIZE", 150 * 1024 * 1024),
            max_epub_expanded_size=_positive_int(
                "EBOOK_MAX_EPUB_EXPANDED_SIZE", 300 * 1024 * 1024
            ),
            max_epub_entries=_positive_int("EBOOK_MAX_EPUB_ENTRIES", 10_000),
        )
        settings.validate()
        return settings

    def validate(self) -> None:
        if (
            not self.index_extensions
            or set(self.index_extensions) - SUPPORTED_EBOOK_EXTENSIONS
        ):
            raise ValueError("index_extensions doit contenir uniquement epub et/ou pdf")
        if self.source == "local":
            if not self.local_library_dir:
                raise ValueError("EBOOK_LOCAL_DIR est requis avec EBOOK_SOURCE=local")
            if not self.local_library_dir.is_dir():
                raise ValueError("EBOOK_LOCAL_DIR doit pointer vers un répertoire lisible")
            return
        if self.source == "google_public":
            if not self.google_drive_public_url:
                raise ValueError(
                    "GOOGLE_DRIVE_PUBLIC_URL est requis avec EBOOK_SOURCE=google_public"
                )
            parsed = urlparse(self.google_drive_public_url)
            if (
                parsed.scheme != "https"
                or parsed.hostname != "drive.google.com"
                or parsed.port not in {None, 443}
                or parsed.username is not None
                or parsed.password is not None
            ):
                raise ValueError("GOOGLE_DRIVE_PUBLIC_URL doit être une URL HTTPS drive.google.com")
            if not GOOGLE_DRIVE_FOLDER_PATH.fullmatch(parsed.path):
                raise ValueError("GOOGLE_DRIVE_PUBLIC_URL doit pointer vers un dossier Drive")
            return
        if self.source != "google":
            return
        if not self.google_service_account_file:
            raise ValueError("GOOGLE_SERVICE_ACCOUNT_FILE est requis avec EBOOK_SOURCE=google")
        if not self.google_service_account_file.is_file():
            raise ValueError("GOOGLE_SERVICE_ACCOUNT_FILE ne pointe pas vers un fichier lisible")
        if not (self.google_drive_id or self.google_drive_folder_id):
            raise ValueError("GOOGLE_DRIVE_ID ou GOOGLE_DRIVE_FOLDER_ID est requis")
