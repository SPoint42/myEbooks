from __future__ import annotations

import hashlib
import logging
import threading
from pathlib import Path

from .config import Settings
from .database import LibraryDatabase
from .domain import EbookSource, ExtractedBook, IndexResult
from .extractors import extract_book

LOGGER = logging.getLogger(__name__)
ALLOWED_COVER_EXTENSIONS = {"jpg", "png", "gif", "webp"}


class IndexAlreadyRunning(RuntimeError):
    pass


class LibraryIndexer:
    def __init__(self, settings: Settings, database: LibraryDatabase, source: EbookSource) -> None:
        self.settings = settings
        self.database = database
        self.source = source
        self._lock = threading.Lock()

    def _cover_path(self, source_id: str, extension: str) -> Path:
        if extension not in ALLOWED_COVER_EXTENSIONS:
            raise ValueError("Extension de couverture interdite")
        digest = hashlib.sha256(source_id.encode("utf-8")).hexdigest()
        return self.settings.covers_dir / f"{digest}.{extension}"

    def _remove_cover(self, filename: str | None) -> None:
        if not filename or Path(filename).name != filename:
            return
        path = self.settings.covers_dir / filename
        if path.is_file():
            path.unlink()

    def _save_cover(self, source_id: str, book: ExtractedBook) -> str | None:
        if not book.cover or not book.cover_extension:
            return None
        path = self._cover_path(source_id, book.cover_extension)
        path.write_bytes(book.cover)
        return path.name

    def run(self, *, force: bool = False) -> IndexResult:
        if not self._lock.acquire(blocking=False):
            raise IndexAlreadyRunning("Une indexation est déjà en cours")

        sync_id = self.database.start_sync()
        try:
            remote_files = self.source.list_files()
            present_ids = {remote_file.id for remote_file in remote_files}
            indexed = unchanged = failed = 0

            for remote_file in remote_files:
                if (
                    not force
                    and self.database.fingerprint_for(remote_file.id) == remote_file.fingerprint
                ):
                    unchanged += 1
                    continue
                previous_cover = self.database.cover_for(remote_file.id)
                try:
                    if (
                        remote_file.size is not None
                        and remote_file.size > self.settings.max_file_size
                    ):
                        raise ValueError("Fichier trop volumineux")
                    content = self.source.download(remote_file)
                    if len(content) > self.settings.max_file_size:
                        raise ValueError("Fichier trop volumineux")
                    book = extract_book(remote_file.name, content, self.settings)
                    cover_filename = self._save_cover(remote_file.id, book)
                    self.database.upsert_book(remote_file, book, cover_filename)
                    if previous_cover != cover_filename:
                        self._remove_cover(previous_cover)
                    indexed += 1
                except Exception as exc:
                    LOGGER.warning("Impossible d'indexer %s: %s", remote_file.name, exc)
                    fallback = ExtractedBook(title=remote_file.name.rsplit(".", 1)[0])
                    self.database.upsert_book(
                        remote_file, fallback, previous_cover, parse_error=str(exc)[:500]
                    )
                    failed += 1

            removed, missing_covers = self.database.mark_missing(present_ids)
            for filename in missing_covers:
                self._remove_cover(filename)
            result = IndexResult(
                discovered=len(remote_files),
                indexed=indexed,
                unchanged=unchanged,
                failed=failed,
                removed=removed,
            )
            self.database.finish_sync(sync_id, result)
            return result
        except Exception as exc:
            self.database.fail_sync(sync_id, str(exc))
            raise
        finally:
            self._lock.release()
