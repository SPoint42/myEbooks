from __future__ import annotations

import logging

from myebooks.database import LibraryDatabase
from myebooks.demo import FakeDriveSource
from myebooks.indexer import (
    LibraryIndexer,
    index_cancellation_path,
    request_index_cancellation,
)


def make_indexer(settings):
    settings.data_dir.mkdir(parents=True)
    settings.covers_dir.mkdir()
    database = LibraryDatabase(settings.database_path)
    database.initialize()
    source = FakeDriveSource()
    return LibraryIndexer(settings, database, source), database, source


def test_index_is_incremental_and_stores_books(settings):
    indexer, database, _source = make_indexer(settings)

    first = indexer.run()
    second = indexer.run()
    books = database.list_books()

    assert first.discovered == 1
    assert first.indexed == 1
    assert first.failed == 0
    assert second.indexed == 0
    assert second.unchanged == 1
    assert [book.title for book in books] == ["Clean Code"]
    assert all(book.cover_filename for book in books)
    assert all((settings.covers_dir / book.cover_filename).is_file() for book in books)


def test_index_marks_books_removed_from_drive(settings):
    indexer, database, source = make_indexer(settings)
    indexer.run()
    source._files.pop("demo-epub")

    result = indexer.run()

    assert result.removed == 1
    assert database.list_books() == []


def test_force_reindexes_unchanged_files(settings):
    indexer, _database, _source = make_indexer(settings)
    indexer.run()

    result = indexer.run(force=True)

    assert result.indexed == 1
    assert result.unchanged == 0


def test_index_reports_progress_in_logs(settings, caplog):
    indexer, _database, _source = make_indexer(settings)
    caplog.set_level(logging.INFO, logger="uvicorn.error.myebooks.indexer")

    indexer.run()

    assert "recensement des livres" in caplog.text
    assert "0 livre(s) traité(s) sur 1" in caplog.text
    assert "1 livre(s) traité(s) sur 1" in caplog.text


def test_index_stops_cleanly_when_catalog_publication_requests_it(settings):
    indexer, database, source = make_indexer(settings)
    source._files["second-epub"] = source._files["demo-epub"]
    original_download = source.download

    def download_and_request_stop(remote_file):
        content = original_download(remote_file)
        if remote_file.id == "demo-epub":
            request_index_cancellation(settings, int(database.latest_sync()["id"]))
        return content

    source.download = download_and_request_stop

    result = indexer.run()

    assert result.discovered == 2
    assert result.indexed == 1
    assert len(database.list_books()) == 1
    assert database.latest_sync()["status"] == "failed"
    assert not index_cancellation_path(settings).exists()
