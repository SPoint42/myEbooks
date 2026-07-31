from __future__ import annotations

from fastapi.testclient import TestClient

from myebooks.demo import FakeDriveSource
from myebooks.web import create_app


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
