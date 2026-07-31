from __future__ import annotations

import re
import threading
from contextlib import closing
from dataclasses import replace

from fastapi.testclient import TestClient

from myebooks.database import LibraryDatabase
from myebooks.demo import FakeDriveSource
from myebooks.domain import ExtractedBook, RemoteFile
from myebooks.indexer import LibraryIndexer
from myebooks.web import _safe_download_name, create_app


def initialize_catalog(settings) -> LibraryDatabase:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.covers_dir.mkdir(parents=True, exist_ok=True)
    database = LibraryDatabase(settings.database_path)
    database.initialize()
    return database


def index_fake_catalog(settings, source: FakeDriveSource | None = None) -> FakeDriveSource:
    source = source or FakeDriveSource()
    database = initialize_catalog(settings)
    LibraryIndexer(settings, database, source).run()
    return source


def add_books(
    settings,
    count: int,
    *,
    prefix: str = "Livre",
    author: str = "Auteur Pagination",
) -> None:
    database = LibraryDatabase(settings.database_path)
    if not settings.database_path.exists():
        initialize_catalog(settings)
    for number in range(count):
        database.upsert_book(
            RemoteFile(
                id=f"pagination-source-{prefix}-{number}",
                name=f"{prefix}-{number:02d}.epub",
                mime_type="application/epub+zip",
                modified_time="pagination-test",
            ),
            ExtractedBook(title=f"{prefix} {number:02d}", author=author),
            cover_filename=None,
        )


def test_library_uses_catalog_built_outside_the_web_process(settings):
    source = index_fake_catalog(settings)
    app = create_app(settings, source)

    with TestClient(app) as client:
        first_page = client.get("/")
        books = client.get("/api/books").json()

    assert first_page.status_code == 200
    assert "Clean Code" in first_page.text
    assert "The Pragmatic Programmer" not in first_page.text
    assert "<script" not in first_page.text
    assert len(books) == 1
    assert all(book["cover_url"] for book in books)


def test_all_indexation_endpoints_are_removed(settings):
    initialize_catalog(settings)
    app = create_app(settings, FakeDriveSource())

    with TestClient(app) as client:
        responses = (
            client.get("/pandaIndexKobo"),
            client.post("/pandaIndexKobo/index"),
            client.get("/api/index/status"),
            client.post("/admin/index"),
            client.post("/kobo/index"),
        )

    assert all(response.status_code == 404 for response in responses)


def test_health_endpoint(settings):
    initialize_catalog(settings)
    app = create_app(settings, FakeDriveSource())

    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_missing_catalog_prevents_startup(settings):
    try:
        create_app(settings, FakeDriveSource())
    except FileNotFoundError as exc:
        assert "script local d'indexation" in str(exc)
    else:
        raise AssertionError("Une application sans catalogue ne doit pas démarrer")


def test_local_startup_indexes_in_background_without_blocking_the_site(settings):
    delegate = FakeDriveSource()

    class DelayedSource:
        def __init__(self):
            self.started = threading.Event()
            self.release = threading.Event()

        def list_files(self):
            self.started.set()
            assert self.release.wait(timeout=5)
            return delegate.list_files()

        def download(self, remote_file):
            return delegate.download(remote_file)

    source = DelayedSource()
    app = create_app(replace(settings, background_index=True), source)

    with TestClient(app) as client:
        assert source.started.wait(timeout=1)
        while_indexing = client.get("/")
        assert while_indexing.status_code == 200
        assert "Votre bibliothèque attend" in while_indexing.text
        source.release.set()
        app.state.index_thread.join(timeout=5)
        assert not app.state.index_thread.is_alive()
        indexed = client.get("/")

    assert "Clean Code" in indexed.text
    assert "The Pragmatic Programmer" not in indexed.text


def test_indexed_epub_can_be_downloaded_for_kobo(settings):
    source = index_fake_catalog(settings)
    app = create_app(settings, source)

    with TestClient(app) as client:
        books = client.get("/api/books").json()
        epub = next(book for book in books if book["file_format"] == "epub")
        response = client.get(f"/books/{epub['id']}/download")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/epub+zip"
    assert "attachment" in response.headers["content-disposition"]
    assert "clean-code.epub" in response.headers["content-disposition"]
    assert response.content == source._files["demo-epub"][2]


def test_unknown_book_cannot_be_downloaded(settings):
    initialize_catalog(settings)
    app = create_app(settings, FakeDriveSource())

    with TestClient(app) as client:
        response = client.get("/books/999/download")

    assert response.status_code == 404


def test_search_works_without_javascript(settings):
    source = index_fake_catalog(settings)
    app = create_app(settings, source)

    with TestClient(app) as client:
        response = client.get("/?q=Clean")

    assert response.status_code == 200
    assert "Clean Code" in response.text
    assert "The Pragmatic Programmer" not in response.text
    assert "Télécharger sur Kobo" in response.text
    assert "<script" not in response.text


def test_legacy_pdf_rows_are_hidden_and_cannot_be_downloaded(settings):
    database = initialize_catalog(settings)
    with closing(database.connect()) as connection, connection:
        connection.execute(
            """
            INSERT INTO books (
                source_id, source_name, source_fingerprint, file_format, title,
                available, indexed_at
            ) VALUES (?, ?, ?, 'pdf', ?, 1, ?)
            """,
            (
                "legacy-pdf",
                "legacy.pdf",
                "legacy",
                "Ancien PDF",
                "2026-07-31T12:00:00+00:00",
            ),
        )
    app = create_app(settings, FakeDriveSource())

    with TestClient(app) as client:
        page = client.get("/")
        books = client.get("/api/books").json()
        download = client.get("/books/1/download")

    assert "Ancien PDF" not in page.text
    assert books == []
    assert download.status_code == 404


def test_home_displays_most_recently_indexed_books_first(settings):
    database = initialize_catalog(settings)
    add_books(settings, 2, prefix="Date")
    with closing(database.connect()) as connection, connection:
        connection.execute(
            "UPDATE books SET title = ?, indexed_at = ? WHERE source_id = ?",
            ("Ancien livre", "2025-01-01T00:00:00+00:00", "pagination-source-Date-0"),
        )
        connection.execute(
            "UPDATE books SET title = ?, indexed_at = ? WHERE source_id = ?",
            ("Nouveau livre", "2026-07-31T12:00:00+00:00", "pagination-source-Date-1"),
        )
    app = create_app(settings, FakeDriveSource())

    with TestClient(app) as client:
        page = client.get("/")
        books = client.get("/api/books").json()

    assert [book["title"] for book in books] == ["Nouveau livre", "Ancien livre"]
    assert page.text.index("Nouveau livre") < page.text.index("Ancien livre")


def test_web_library_paginates_at_ten_books_and_preserves_search(settings):
    add_books(settings, 23)
    app = create_app(settings, FakeDriveSource())

    with TestClient(app) as client:
        first_page = client.get("/?q=Livre")
        second_page = client.get("/?q=Livre&page=2")
        last_page = client.get("/?q=Livre&page=3")

    assert first_page.text.count('<article class="book-card">') == 10
    assert second_page.text.count('<article class="book-card">') == 10
    assert last_page.text.count('<article class="book-card">') == 3
    assert "Page 1 sur 3" in first_page.text
    assert "Page 2 sur 3" in second_page.text
    assert "Page 3 sur 3" in last_page.text
    assert "q=Livre" in first_page.text
    assert "page=2" in first_page.text


def test_kobo_library_uses_native_pagination_forms(settings):
    add_books(settings, 23)
    app = create_app(settings, FakeDriveSource())

    with TestClient(app) as client:
        first_page = client.get("/kobo?q=Livre")
        second_page = client.get("/kobo?q=Livre&page=2")

    assert first_page.text.count('<div class="book">') == 10
    assert second_page.text.count('<div class="book">') == 10
    assert "page 1 sur 3" in first_page.text
    assert 'action="/kobo" method="get"' in first_page.text
    assert 'name="q" value="Livre"' in first_page.text
    assert 'name="page" value="2"' in first_page.text
    assert "PAGE SUIVANTE" in first_page.text
    assert "PAGE PRECEDENTE" in second_page.text


def test_invalid_or_excessive_page_is_safely_normalized(settings):
    add_books(settings, 23)
    app = create_app(settings, FakeDriveSource())

    with TestClient(app) as client:
        invalid_page = client.get("/?page=invalid")
        excessive_page = client.get("/?page=999999999")

    assert invalid_page.text.count('<article class="book-card">') == 10
    assert "Page 1 sur 3" in invalid_page.text
    assert excessive_page.text.count('<article class="book-card">') == 3
    assert "Page 3 sur 3" in excessive_page.text


def test_author_select_comes_from_database_and_filters_web_and_kobo(settings):
    add_books(settings, 12, prefix="Alpha", author="Auteur Alpha")
    add_books(settings, 5, prefix="Beta", author="Auteur Beta")
    app = create_app(settings, FakeDriveSource())

    assert app.state.database.list_authors() == ["Auteur Alpha", "Auteur Beta"]

    with TestClient(app) as client:
        web_page = client.get("/?author=Auteur+Alpha")
        kobo_page = client.get("/kobo?author=Auteur+Beta")

    assert web_page.text.count('<article class="book-card">') == 10
    assert "<strong>12</strong>" in web_page.text
    assert "livres trouvés" in web_page.text
    assert '<option value="Auteur Alpha" selected>Auteur Alpha</option>' in web_page.text
    assert "author=Auteur+Alpha" in web_page.text
    assert kobo_page.text.count('<div class="book">') == 5
    assert '<option value="Auteur Beta" selected>Auteur Beta</option>' in kobo_page.text
    assert "Alpha 00" not in kobo_page.text


def test_unknown_author_filter_is_ignored(settings):
    add_books(settings, 2, author="Auteur connu")
    app = create_app(settings, FakeDriveSource())

    with TestClient(app) as client:
        response = client.get("/?author=Auteur+inconnu")

    assert response.status_code == 200
    assert response.text.count('<article class="book-card">') == 2
    assert 'value="Auteur inconnu" selected' not in response.text


def test_kobo_user_agent_gets_legacy_page(settings):
    initialize_catalog(settings)
    app = create_app(settings, FakeDriveSource())

    with TestClient(app) as client:
        response = client.get("/", headers={"user-agent": "Mozilla/5.0 Kobo eReader"})

    assert response.status_code == 200
    assert "Version simplifiée pour le navigateur Kobo" in response.text
    assert "display: grid" not in response.text
    assert "<script" not in response.text
    assert response.headers["cache-control"] == "no-store, max-age=0"


def test_kobo_download_uses_file_extension_and_legacy_headers(settings):
    source = index_fake_catalog(settings)
    app = create_app(settings, source)

    with TestClient(app) as client:
        page = client.get("/kobo")
        match = re.search(r'action="(/kobo/books/\d+/[^"]+\.epub)"', page.text)
        assert match is not None
        response = client.get(match.group(1))

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/epub+zip"
    assert "filename*=UTF-8" not in response.headers["content-disposition"]
    assert response.headers["content-disposition"].endswith('.epub"')
    assert response.content == source._files["demo-epub"][2]
    assert " download" not in page.text
    assert '<input class="action" type="submit" value="TELECHARGER EPUB">' in page.text
    assert 'action="/kobo/books/' in page.text
    assert 'href="http://testserver/kobo/books/' not in page.text


def test_kobo_download_rejects_a_mismatched_filename(settings):
    source = index_fake_catalog(settings)
    app = create_app(settings, source)

    with TestClient(app) as client:
        response = client.get("/kobo/books/1/not-the-book.epub")

    assert response.status_code == 404


def test_kobo_cover_is_a_small_relative_png(settings):
    source = index_fake_catalog(settings)
    app = create_app(settings, source)

    with TestClient(app) as client:
        page = client.get("/kobo")
        match = re.search(r'src="(/kobo/covers/(\d+)\.png)"', page.text)
        assert match is not None
        response = client.get(match.group(1))

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert response.content.startswith(b"\x89PNG\r\n\x1a\n")
    assert len(response.content) < 200_000
    assert 'src="http://testserver/covers/' not in page.text


def test_unknown_kobo_cover_returns_404(settings):
    initialize_catalog(settings)
    app = create_app(settings, FakeDriveSource())

    with TestClient(app) as client:
        response = client.get("/kobo/covers/999.png")

    assert response.status_code == 404


def test_download_filename_removes_header_injection_characters():
    assert _safe_download_name("unsafe\r\nX-Evil: yes.epub", "epub") == "unsafeX-Evil: yes.epub"
