from __future__ import annotations

from fastapi.testclient import TestClient

from myebooks.demo import FakeDriveSource
from myebooks.web import _safe_download_name, create_app


def test_library_can_be_indexed_from_web(settings):
    app = create_app(settings, FakeDriveSource())

    with TestClient(app) as client:
        first_page = client.get("/")
        csrf_token = client.cookies.get("myebooks_csrf")
        response = client.post(
            "/admin/index",
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
        response = client.post("/admin/index", data={"csrf_token": "invalid"})

    assert response.status_code == 403


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
            "/admin/index",
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
            "/admin/index",
            data={"csrf_token": client.cookies.get("myebooks_csrf")},
        )
        response = client.get("/?q=Pragmatic")

    assert response.status_code == 200
    assert "The Pragmatic Programmer" in response.text
    assert "Clean Code" not in response.text
    assert "Télécharger sur Kobo" in response.text
    assert "<script" not in response.text


def test_download_filename_removes_header_injection_characters():
    assert _safe_download_name("unsafe\r\nX-Evil: yes.epub", "epub") == "unsafeX-Evil: yes.epub"
