from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

from .domain import Book, ExtractedBook, IndexResult, RemoteFile


class LibraryDatabase:
    def __init__(self, path: Path) -> None:
        self.path = path

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self.connect()) as connection, connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS books (
                    id INTEGER PRIMARY KEY,
                    source_id TEXT NOT NULL UNIQUE,
                    source_name TEXT NOT NULL,
                    source_fingerprint TEXT NOT NULL,
                    file_format TEXT NOT NULL CHECK (file_format IN ('pdf', 'epub')),
                    title TEXT NOT NULL,
                    author TEXT,
                    publication_year INTEGER,
                    isbn TEXT,
                    cover_filename TEXT,
                    available INTEGER NOT NULL DEFAULT 1 CHECK (available IN (0, 1)),
                    parse_error TEXT,
                    indexed_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_books_available_title
                    ON books (available, title COLLATE NOCASE);

                CREATE TABLE IF NOT EXISTS sync_runs (
                    id INTEGER PRIMARY KEY,
                    status TEXT NOT NULL CHECK (status IN ('running', 'completed', 'failed')),
                    started_at TEXT NOT NULL,
                    completed_at TEXT,
                    discovered INTEGER NOT NULL DEFAULT 0,
                    indexed INTEGER NOT NULL DEFAULT 0,
                    unchanged INTEGER NOT NULL DEFAULT 0,
                    failed INTEGER NOT NULL DEFAULT 0,
                    removed INTEGER NOT NULL DEFAULT 0,
                    error TEXT
                );
                """
            )

    def list_books(self) -> list[Book]:
        with closing(self.connect()) as connection:
            rows = connection.execute(
                """
                SELECT id, source_id, source_name, file_format, title, author,
                       publication_year, isbn, cover_filename, parse_error, indexed_at
                FROM books
                WHERE available = 1
                ORDER BY title COLLATE NOCASE
                """
            ).fetchall()
        return [Book(**dict(row)) for row in rows]

    def fingerprint_for(self, source_id: str) -> str | None:
        with closing(self.connect()) as connection:
            row = connection.execute(
                "SELECT source_fingerprint FROM books WHERE source_id = ? AND available = 1",
                (source_id,),
            ).fetchone()
        return str(row[0]) if row else None

    def cover_for(self, source_id: str) -> str | None:
        with closing(self.connect()) as connection:
            row = connection.execute(
                "SELECT cover_filename FROM books WHERE source_id = ?", (source_id,)
            ).fetchone()
        return str(row[0]) if row and row[0] else None

    def upsert_book(
        self,
        remote_file: RemoteFile,
        book: ExtractedBook,
        cover_filename: str | None,
        parse_error: str | None = None,
    ) -> None:
        now = datetime.now(UTC).isoformat()
        file_format = remote_file.name.rsplit(".", 1)[-1].lower()
        with closing(self.connect()) as connection, connection:
            connection.execute(
                """
                INSERT INTO books (
                    source_id, source_name, source_fingerprint, file_format, title,
                    author, publication_year, isbn, cover_filename, available,
                    parse_error, indexed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
                ON CONFLICT(source_id) DO UPDATE SET
                    source_name = excluded.source_name,
                    source_fingerprint = excluded.source_fingerprint,
                    file_format = excluded.file_format,
                    title = excluded.title,
                    author = excluded.author,
                    publication_year = excluded.publication_year,
                    isbn = excluded.isbn,
                    cover_filename = excluded.cover_filename,
                    available = 1,
                    parse_error = excluded.parse_error,
                    indexed_at = excluded.indexed_at
                """,
                (
                    remote_file.id,
                    remote_file.name,
                    remote_file.fingerprint,
                    file_format,
                    book.title,
                    book.author,
                    book.publication_year,
                    book.isbn,
                    cover_filename,
                    parse_error,
                    now,
                ),
            )

    def mark_missing(self, present_source_ids: set[str]) -> tuple[int, list[str]]:
        with closing(self.connect()) as connection, connection:
            rows = connection.execute(
                "SELECT source_id, cover_filename FROM books WHERE available = 1"
            ).fetchall()
            missing = [row for row in rows if row["source_id"] not in present_source_ids]
            connection.executemany(
                "UPDATE books SET available = 0 WHERE source_id = ?",
                [(row["source_id"],) for row in missing],
            )
        covers = [str(row["cover_filename"]) for row in missing if row["cover_filename"]]
        return len(missing), covers

    def start_sync(self) -> int:
        with closing(self.connect()) as connection, connection:
            cursor = connection.execute(
                "INSERT INTO sync_runs (status, started_at) VALUES ('running', ?)",
                (datetime.now(UTC).isoformat(),),
            )
            return int(cursor.lastrowid)

    def finish_sync(self, sync_id: int, result: IndexResult) -> None:
        with closing(self.connect()) as connection, connection:
            connection.execute(
                """
                UPDATE sync_runs SET status = 'completed', completed_at = ?, discovered = ?,
                    indexed = ?, unchanged = ?, failed = ?, removed = ?
                WHERE id = ?
                """,
                (
                    datetime.now(UTC).isoformat(),
                    result.discovered,
                    result.indexed,
                    result.unchanged,
                    result.failed,
                    result.removed,
                    sync_id,
                ),
            )

    def fail_sync(self, sync_id: int, error: str) -> None:
        with closing(self.connect()) as connection, connection:
            connection.execute(
                """
                UPDATE sync_runs SET status = 'failed', completed_at = ?, error = ? WHERE id = ?
                """,
                (datetime.now(UTC).isoformat(), error[:1000], sync_id),
            )

    def latest_sync(self) -> dict[str, object] | None:
        with closing(self.connect()) as connection:
            row = connection.execute(
                "SELECT * FROM sync_runs ORDER BY id DESC LIMIT 1"
            ).fetchone()
        return dict(row) if row else None
