from __future__ import annotations

from myebooks.adapters.google_drive import FOLDER_MIME_TYPE, GoogleDriveSource


def bare_source(folder_id=None):
    source = GoogleDriveSource.__new__(GoogleDriveSource)
    source.folder_id = folder_id
    source.drive_id = "shared-drive"
    source.max_file_size = 1024
    return source


def test_ebook_detection_accepts_mime_type_or_extension():
    assert GoogleDriveSource._is_ebook({"name": "book.bin", "mimeType": "application/pdf"})
    assert GoogleDriveSource._is_ebook(
        {"name": "book.EPUB", "mimeType": "application/octet-stream"}
    )
    assert not GoogleDriveSource._is_ebook({"name": "notes.txt", "mimeType": "text/plain"})


def test_folder_listing_is_recursive(monkeypatch):
    source = bare_source("root")
    responses = {
        "'root' in parents and trashed = false": [
            {"id": "nested", "name": "Livres", "mimeType": FOLDER_MIME_TYPE},
            {
                "id": "pdf-1",
                "name": "one.pdf",
                "mimeType": "application/pdf",
                "modifiedTime": "2026-01-01T00:00:00Z",
                "size": "42",
            },
        ],
        "'nested' in parents and trashed = false": [
            {
                "id": "epub-1",
                "name": "two.epub",
                "mimeType": "application/epub+zip",
                "modifiedTime": "2026-01-02T00:00:00Z",
                "md5Checksum": "abc",
                "size": "84",
            }
        ],
    }
    monkeypatch.setattr(source, "_list_query", responses.__getitem__)

    files = source.list_files()

    assert {item.id for item in files} == {"pdf-1", "epub-1"}
    assert next(item for item in files if item.id == "epub-1").fingerprint == "abc"


def test_drive_listing_filters_non_ebooks(monkeypatch):
    source = bare_source()
    monkeypatch.setattr(
        source,
        "_list_query",
        lambda _query: [
            {
                "id": "pdf-1",
                "name": "book.pdf",
                "mimeType": "application/pdf",
                "modifiedTime": "now",
            },
            {"id": "txt-1", "name": "notes.txt", "mimeType": "text/plain"},
        ],
    )

    assert [item.id for item in source.list_files()] == ["pdf-1"]
