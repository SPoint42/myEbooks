from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class RemoteFile:
    id: str
    name: str
    mime_type: str
    modified_time: str
    checksum: str | None = None
    size: int | None = None

    @property
    def fingerprint(self) -> str:
        return self.checksum or self.modified_time


class EbookSource(Protocol):
    def list_files(self) -> list[RemoteFile]: ...

    def download(self, remote_file: RemoteFile) -> bytes: ...


@dataclass(frozen=True, slots=True)
class ExtractedBook:
    title: str
    author: str | None = None
    publication_year: int | None = None
    isbn: str | None = None
    cover: bytes | None = None
    cover_extension: str | None = None


@dataclass(frozen=True, slots=True)
class Book:
    id: int
    source_id: str
    source_name: str
    file_format: str
    title: str
    author: str | None
    publication_year: int | None
    isbn: str | None
    cover_filename: str | None
    parse_error: str | None
    indexed_at: str


@dataclass(frozen=True, slots=True)
class IndexResult:
    discovered: int = 0
    indexed: int = 0
    unchanged: int = 0
    failed: int = 0
    removed: int = 0
