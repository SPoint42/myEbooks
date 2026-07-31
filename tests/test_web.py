from __future__ import annotations

import re

from fastapi.testclient import TestClient

from myebooks.demo import FakeDriveSource
from myebooks.domain import ExtractedBook, IndexResult, RemoteFile
from myebooks.web import _safe_download_name, create_app


def add_books(
    app,
    count: int,
    *,
    prefix: str = "Livre",
    author: str = "Auteur Pagination",
) -> None:
    for number in range(count):
        app.state.database.upsert_book(
            RemoteFile(
                id=f"pagination-source-{prefix}-{number}",
                name=f"{prefix}-{number:02d}.epub",
                mime_type="application/epub+zip",
                modified_time="pagination-test",
            ),
            ExtractedBook(title=f"{prefix} {number:02d}", author=author),
            cover_filename=None,
        )


def test_library_can_be_indexed_from_web(settings):
    app = create_app(settings, FakeDriveSource())

    with TestClient(app) as client:
        first_page = client.get("/")
        csrf_token = client.cookies.get("myebooks_csrf")
        response = client.post(
            "/pandaIndexKobo/index",
            data={"csrf_token": csrf_token},
            follow_redirects=False,
        )
        books = client.get("/api/books").json()
        status = client.get("/api/index/status").json()

    assert first_page.status_code == 200
    assert "Votre bibliothèque attend" in first_page.text
    assert "<script" not in first_page.text
    assert response.status_code == 303
    assert len(books) == 2
    assert all(book["cover_url"] for book in books)
    assert status["status"] == "completed"


def test_index_endpoint_rejects_invalid_csrf(settings):
    app = create_app(settings, FakeDriveSource())

    with TestClient(app) as client:
        client.get("/")
        response = client.post("/pandaIndexKobo/index", data={"csrf_token": "invalid"})

    assert response.status_code == 403


def test_index_controls_are_only_on_unlinked_admin_page(settings):
    app = create_app(settings, FakeDriveSource())

    with TestClient(app) as client:
        public_page = client.get("/")
        kobo_page = client.get("/kobo")
        admin_page = client.get("/pandaIndexKobo")
        old_admin_endpoint = client.post("/admin/index")
        old_kobo_endpoint = client.post("/kobo/index")

    for page in (public_page, kobo_page):
        assert "pandaIndexKobo" not in page.text
        assert "INDEXER LA BIBLIOTHEQUE" not in page.text
        assert "Indexation en cours" not in page.text
    assert 'action="/pandaIndexKobo/index"' in admin_page.text
    assert "INDEXER LA BIBLIOTHEQUE" in admin_page.text
    assert old_admin_endpoint.status_code == 404
    assert old_kobo_endpoint.status_code == 404


def test_running_index_displays_processed_books_and_total(settings):
    app = create_app(settings, FakeDriveSource())
    sync_id = app.state.database.start_sync()
    app.state.database.update_sync_progress(
        sync_id,
        IndexResult(discovered=1_044, indexed=31, unchanged=6, failed=0),
    )

    with TestClient(app) as client:
        page = client.get("/pandaIndexKobo")
        status = client.get("/api/index/status").json()

    assert "37 livre(s) traité(s) sur 1044" in page.text
    assert '<meta http-equiv="refresh" content="5">' in page.text
    assert status["processed"] == 37
    assert status["discovered"] == 1_044


def test_health_endpoint(settings):
    app = create_app(settings, FakeDriveSource())

    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_indexed_epub_can_be_downloaded_for_kobo(settings):
    source = FakeDriveSource()
    app = create_app(settings, source)

    with TestClient(app) as client:
        client.get("/")
        client.post(
            "/pandaIndexKobo/index",
            data={"csrf_token": client.cookies.get("myebooks_csrf")},
        )
        books = client.get("/api/books").json()
        epub = next(book for book in books if book["file_format"] == "epub")
        response = client.get(f"/books/{epub['id']}/download")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/epub+zip"
    assert "attachment" in response.headers["content-disposition"]
    assert "clean-code.epub" in response.headers["content-disposition"]
    assert response.content == source._files["demo-epub"][2]


def test_unknown_book_cannot_be_downloaded(settings):
    app = create_app(settings, FakeDriveSource())

    with TestClient(app) as client:
        response = client.get("/books/999/download")

    assert response.status_code == 404


def test_search_works_without_javascript(settings):
    app = create_app(settings, FakeDriveSource())

    with TestClient(app) as client:
        client.get("/")
        client.post(
            "/pandaIndexKobo/index",
            data={"csrf_token": client.cookies.get("myebooks_csrf")},
        )
        response = client.get("/?q=Pragmatic")

    assert response.status_code == 200
    assert "The Pragmatic Programmer" in response.text
    assert "Clean Code" not in response.text
    assert "Télécharger sur Kobo" in response.text
    assert "<script" not in response.text


def test_web_library_paginates_at_ten_books_and_preserves_search(settings):
    app = create_app(settings, FakeDriveSource())
    add_books(app, 23)

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
    app = create_app(settings, FakeDriveSource())
    add_books(app, 23)

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
    app = create_app(settings, FakeDriveSource())
    add_books(app, 23)

    with TestClient(app) as client:
        invalid_page = client.get("/?page=invalid")
        excessive_page = client.get("/?page=999999999")

    assert invalid_page.text.count('<article class="book-card">') == 10
    assert "Page 1 sur 3" in invalid_page.text
    assert excessive_page.text.count('<article class="book-card">') == 3
    assert "Page 3 sur 3" in excessive_page.text


def test_author_select_comes_from_database_and_filters_web_and_kobo(settings):
    app = create_app(settings, FakeDriveSource())
    add_books(app, 12, prefix="Alpha", author="Auteur Alpha")
    add_books(app, 5, prefix="Beta", author="Auteur Beta")

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
    app = create_app(settings, FakeDriveSource())
    add_books(app, 2, author="Auteur connu")

    with TestClient(app) as client:
        response = client.get("/?author=Auteur+inconnu")

    assert response.status_code == 200
    assert response.text.count('<article class="book-card">') == 2
    assert 'value="Auteur inconnu" selected' not in response.text


def test_kobo_user_agent_gets_legacy_page(settings):
    app = create_app(settings, FakeDriveSource())

    with TestClient(app) as client:
        response = client.get("/", headers={"user-agent": "Mozilla/5.0 Kobo eReader"})

    assert response.status_code == 200
    assert "Version simplifiée pour le navigateur Kobo" in response.text
    assert "display: grid" not in response.text
    assert "<script" not in response.text
    assert response.headers["cache-control"] == "no-store, max-age=0"


def test_kobo_download_uses_file_extension_and_legacy_headers(settings):
    source = FakeDriveSource()
    app = create_app(settings, source)

    with TestClient(app) as client:
        client.get("/kobo")
        client.post(
            "/pandaIndexKobo/index",
            data={"csrf_token": client.cookies.get("myebooks_csrf")},
        )
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
    app = create_app(settings, FakeDriveSource())

    with TestClient(app) as client:
        client.get("/kobo")
        client.post(
            "/pandaIndexKobo/index",
            data={"csrf_token": client.cookies.get("myebooks_csrf")},
        )
        response = client.get("/kobo/books/1/not-the-book.epub")

    assert response.status_code == 404


def test_kobo_cover_is_a_small_relative_png(settings):
    app = create_app(settings, FakeDriveSource())

    with TestClient(app) as client:
        client.get("/kobo")
        client.post(
            "/pandaIndexKobo/index",
            data={"csrf_token": client.cookies.get("myebooks_csrf")},
        )
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
    app = create_app(settings, FakeDriveSource())

    with TestClient(app) as client:
        response = client.get("/kobo/covers/999.png")

    assert response.status_code == 404


def test_download_filename_removes_header_injection_characters():
    assert _safe_download_name("unsafe\r\nX-Evil: yes.epub", "epub") == "unsafeX-Evil: yes.epub"
