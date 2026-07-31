from __future__ import annotations

import logging
import re
import secrets
import unicodedata
from dataclasses import asdict
from pathlib import Path
from typing import Annotated
from urllib.parse import quote

from fastapi import BackgroundTasks, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .adapters.google_drive import GoogleDriveSource
from .adapters.public_google_drive import PublicGoogleDriveSource
from .config import Settings
from .database import LibraryDatabase
from .demo import FakeDriveSource
from .domain import EbookSource, RemoteFile
from .indexer import IndexAlreadyRunning, LibraryIndexer

LOGGER = logging.getLogger(__name__)
PACKAGE_DIR = Path(__file__).parent


def _safe_download_name(filename: str, file_format: str) -> str:
    name = filename.replace("/", "_").replace("\\", "_")
    name = "".join(character for character in name if ord(character) >= 32 and character != "\x7f")
    expected_suffix = f".{file_format}"
    if not name.lower().endswith(expected_suffix):
        name = f"{name}{expected_suffix}"
    return name[:240] or f"livre.{file_format}"


def _content_disposition(filename: str) -> str:
    ascii_name = unicodedata.normalize("NFKD", filename).encode("ascii", "ignore").decode()
    ascii_name = re.sub(r"[^A-Za-z0-9._-]+", "_", ascii_name).strip("._") or "ebook"
    return f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(filename)}"


def _chunks(content: bytes, size: int = 512 * 1024):
    for offset in range(0, len(content), size):
        yield content[offset : offset + size]


def create_app(
    settings: Settings | None = None,
    source: EbookSource | None = None,
) -> FastAPI:
    settings = settings or Settings.from_env()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.covers_dir.mkdir(parents=True, exist_ok=True)

    database = LibraryDatabase(settings.database_path)
    database.initialize()
    if source is None:
        if settings.source == "google":
            source = GoogleDriveSource(settings)
        elif settings.source == "google_public":
            source = PublicGoogleDriveSource(settings)
        else:
            source = FakeDriveSource()
    indexer = LibraryIndexer(settings, database, source)
    templates = Jinja2Templates(directory=PACKAGE_DIR / "templates")

    app = FastAPI(title="myEbooks", version="0.2.0")
    app.state.settings = settings
    app.state.database = database
    app.state.indexer = indexer
    app.mount("/static", StaticFiles(directory=PACKAGE_DIR / "static"), name="static")
    app.mount("/covers", StaticFiles(directory=settings.covers_dir), name="covers")

    @app.get("/", response_class=HTMLResponse)
    def library(request: Request) -> HTMLResponse:
        csrf_token = request.cookies.get("myebooks_csrf") or secrets.token_urlsafe(32)
        query = " ".join(request.query_params.get("q", "").split())[:100]
        all_books = database.list_books()
        if query:
            needle = query.casefold()
            books = [
                book
                for book in all_books
                if needle
                in " ".join((book.title, book.author or "", book.isbn or "")).casefold()
            ]
        else:
            books = all_books
        response = templates.TemplateResponse(
            request=request,
            name="index.html",
            context={
                "books": books,
                "total_books": len(all_books),
                "query": query,
                "sync": database.latest_sync(),
                "source_name": (
                    "Google Drive public"
                    if settings.source == "google_public"
                    else "Google Drive"
                    if settings.source == "google"
                    else "Drive de démonstration"
                ),
                "csrf_token": csrf_token,
            },
        )
        response.set_cookie(
            "myebooks_csrf",
            csrf_token,
            httponly=True,
            samesite="strict",
            secure=request.url.scheme == "https",
            max_age=86_400,
        )
        return response

    def run_index(force: bool) -> None:
        try:
            indexer.run(force=force)
        except IndexAlreadyRunning:
            LOGGER.info("Demande d'indexation ignorée : une exécution est déjà en cours")
        except Exception:
            LOGGER.exception("L'indexation a échoué")

    @app.post("/admin/index", response_class=RedirectResponse)
    def start_index(
        request: Request,
        background_tasks: BackgroundTasks,
        csrf_token: Annotated[str, Form()],
        force: Annotated[str | None, Form()] = None,
    ) -> RedirectResponse:
        cookie_token = request.cookies.get("myebooks_csrf", "")
        if not cookie_token or not secrets.compare_digest(cookie_token, csrf_token):
            raise HTTPException(status_code=403, detail="Jeton CSRF invalide")
        background_tasks.add_task(run_index, force == "on")
        return RedirectResponse(url="/?indexing=1", status_code=303)

    @app.get("/api/books", response_class=JSONResponse)
    def api_books(request: Request) -> list[dict[str, object]]:
        result = []
        for book in database.list_books():
            item = asdict(book)
            item["cover_url"] = (
                str(request.url_for("covers", path=book.cover_filename))
                if book.cover_filename
                else None
            )
            result.append(item)
        return result

    @app.get("/api/index/status", response_class=JSONResponse)
    def api_index_status() -> dict[str, object]:
        return database.latest_sync() or {"status": "never_run"}

    @app.get("/books/{book_id}/download", name="download_book")
    def download_book(book_id: int) -> StreamingResponse:
        book = database.book_by_id(book_id)
        if book is None:
            raise HTTPException(status_code=404, detail="Livre introuvable")
        remote_file = RemoteFile(
            id=book.source_id,
            name=book.source_name,
            mime_type=(
                "application/epub+zip" if book.file_format == "epub" else "application/pdf"
            ),
            modified_time="indexed",
        )
        try:
            content = source.download(remote_file)
        except Exception as exc:
            LOGGER.warning("Téléchargement impossible pour %s: %s", book.source_name, exc)
            raise HTTPException(
                status_code=502, detail="Le fichier ne peut pas être téléchargé depuis le Drive"
            ) from exc
        filename = _safe_download_name(book.source_name, book.file_format)
        return StreamingResponse(
            _chunks(content),
            media_type=remote_file.mime_type,
            headers={
                "Content-Disposition": _content_disposition(filename),
                "Content-Length": str(len(content)),
                "Cache-Control": "private, no-store",
                "X-Content-Type-Options": "nosniff",
            },
        )

    @app.get("/health", response_class=JSONResponse)
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app
