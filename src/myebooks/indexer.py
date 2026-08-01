from __future__ import annotations

import hashlib
import logging
import os
import tempfile
import threading
from pathlib import Path

from .config import Settings
from .database import LibraryDatabase
from .domain import EBOOK_MIME_TYPES, EbookSource, ExtractedBook, IndexResult, RemoteFile
from .extractors import extract_book

LOGGER = logging.getLogger("uvicorn.error.myebooks.indexer")
ALLOWED_COVER_EXTENSIONS = {"jpg", "png", "gif", "webp"}
INDEX_CANCELLATION_FILENAME = ".myebooks-index-cancel"


def _ebook_extension(remote_file: RemoteFile) -> str:
    return remote_file.name.rsplit(".", 1)[-1].lower() if "." in remote_file.name else ""


def _is_selected_ebook(remote_file: RemoteFile, settings: Settings) -> bool:
    extension = _ebook_extension(remote_file)
    return (
        extension in settings.index_extensions
        and EBOOK_MIME_TYPES.get(extension) == remote_file.mime_type
    )


class IndexAlreadyRunning(RuntimeError):
    pass


class IndexCancelled(RuntimeError):
    pass


def index_cancellation_path(settings: Settings) -> Path:
    return settings.data_dir / INDEX_CANCELLATION_FILENAME


def request_index_cancellation(settings: Settings, sync_id: int) -> None:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    file_descriptor, temporary_name = tempfile.mkstemp(
        prefix=".myebooks-index-cancel-",
        dir=settings.data_dir,
        text=True,
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(file_descriptor, "w", encoding="ascii") as stream:
            stream.write(f"{sync_id}\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, index_cancellation_path(settings))
    finally:
        temporary_path.unlink(missing_ok=True)


def _cancellation_requested(settings: Settings, sync_id: int) -> bool:
    try:
        requested_sync = index_cancellation_path(settings).read_text(encoding="ascii").strip()
    except FileNotFoundError:
        return False
    return requested_sync == str(sync_id)


def _clear_cancellation(settings: Settings, sync_id: int) -> None:
    if _cancellation_requested(settings, sync_id):
        index_cancellation_path(settings).unlink(missing_ok=True)


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
            LOGGER.info(
                "Indexation démarrée pour les formats %s : recensement des livres…",
                ", ".join(sorted(self.settings.index_extensions)),
            )
            remote_files = [
                remote_file
                for remote_file in self.source.list_files()
                if _is_selected_ebook(remote_file, self.settings)
            ]
            present_ids = {remote_file.id for remote_file in remote_files}
            indexed = unchanged = failed = 0
            total = len(remote_files)

            def stop_if_requested() -> None:
                if _cancellation_requested(self.settings, sync_id):
                    raise IndexCancelled("Arrêt demandé avant la publication du catalogue")

            def report_progress() -> None:
                result = IndexResult(
                    discovered=total,
                    indexed=indexed,
                    unchanged=unchanged,
                    failed=failed,
                )
                self.database.update_sync_progress(sync_id, result)
                processed = indexed + unchanged + failed
                if processed == 0 or processed == total or processed % 10 == 0:
                    LOGGER.info(
                        "Indexation : %d livre(s) traité(s) sur %d "
                        "(%d indexé(s), %d inchangé(s), %d en erreur)",
                        processed,
                        total,
                        indexed,
                        unchanged,
                        failed,
                    )

            report_progress()
            stop_if_requested()

            for remote_file in remote_files:
                stop_if_requested()
                if (
                    not force
                    and self.database.fingerprint_for(remote_file.id) == remote_file.fingerprint
                ):
                    unchanged += 1
                    report_progress()
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
                report_progress()

            stop_if_requested()
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
        except IndexCancelled as exc:
            result = IndexResult(
                discovered=total,
                indexed=indexed,
                unchanged=unchanged,
                failed=failed,
            )
            self.database.fail_sync(sync_id, str(exc))
            LOGGER.info(
                "Indexation arrêtée proprement : %d livre(s) traité(s) sur %d",
                indexed + unchanged + failed,
                total,
            )
            return result
        except Exception as exc:
            self.database.fail_sync(sync_id, str(exc))
            raise
        finally:
            _clear_cancellation(self.settings, sync_id)
            self._lock.release()
