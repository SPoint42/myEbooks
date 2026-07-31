from __future__ import annotations

import logging

from myebooks.database import LibraryDatabase
from myebooks.demo import FakeDriveSource
from myebooks.indexer import LibraryIndexer


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

    assert first.discovered == 2
    assert first.indexed == 2
    assert first.failed == 0
    assert second.indexed == 0
    assert second.unchanged == 2
    assert [book.title for book in books] == ["The Pragmatic Programmer", "Clean Code"]
    assert all(book.cover_filename for book in books)
    assert all((settings.covers_dir / book.cover_filename).is_file() for book in books)


def test_index_marks_books_removed_from_drive(settings):
    indexer, database, source = make_indexer(settings)
    indexer.run()
    source._files.pop("demo-pdf")

    result = indexer.run()

    assert result.removed == 1
    assert [book.title for book in database.list_books()] == ["Clean Code"]


def test_force_reindexes_unchanged_files(settings):
    indexer, _database, _source = make_indexer(settings)
    indexer.run()

    result = indexer.run(force=True)

    assert result.indexed == 2
    assert result.unchanged == 0


def test_index_reports_progress_in_logs(settings, caplog):
    indexer, _database, _source = make_indexer(settings)
    caplog.set_level(logging.INFO, logger="uvicorn.error.myebooks.indexer")

    indexer.run()

    assert "recensement des livres" in caplog.text
    assert "0 livre(s) traité(s) sur 2" in caplog.text
    assert "2 livre(s) traité(s) sur 2" in caplog.text
