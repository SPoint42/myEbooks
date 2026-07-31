from __future__ import annotations

import logging
import re
import secrets
import unicodedata
from dataclasses import asdict
from pathlib import Path
from urllib.parse import quote, urlencode

import pymupdf
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import (
    HTMLResponse,
    JSONResponse,
    Response,
    StreamingResponse,
)
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .config import Settings
from .database import LibraryDatabase
from .domain import EbookSource, RemoteFile
from .sources import create_source, source_label

LOGGER = logging.getLogger(__name__)
PACKAGE_DIR = Path(__file__).parent
BOOKS_PER_PAGE = 10


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


def _kobo_url_filename(filename: str, file_format: str) -> str:
    safe_name = _safe_download_name(filename, file_format)
    ascii_name = unicodedata.normalize("NFKD", safe_name).encode("ascii", "ignore").decode()
    stem = ascii_name.rsplit(".", 1)[0]
    stem = re.sub(r"[^A-Za-z0-9_-]+", "-", stem).strip("-_") or "ebook"
    return f"{stem[:100]}.{file_format}"


def _is_kobo_browser(request: Request) -> bool:
    user_agent = request.headers.get("user-agent", "").casefold()
    return "kobo" in user_agent or "nickel" in user_agent


def _kobo_cover_png(path: Path) -> bytes:
    with pymupdf.open(path) as document:
        if document.page_count < 1:
            raise ValueError("Image de couverture vide")
        page = document[0]
        scale = min(180 / page.rect.width, 260 / page.rect.height, 1)
        pixmap = page.get_pixmap(
            matrix=pymupdf.Matrix(scale, scale),
            colorspace=pymupdf.csRGB,
            alpha=False,
        )
        return pixmap.tobytes("png")


def _chunks(content: bytes, size: int = 512 * 1024):
    for offset in range(0, len(content), size):
        yield content[offset : offset + size]


def create_app(
    settings: Settings | None = None,
    source: EbookSource | None = None,
) -> FastAPI:
    settings = settings or Settings.from_env()
    database = LibraryDatabase(settings.database_path, read_only=True)
    database.validate_catalog()
    if not settings.covers_dir.is_dir():
        raise FileNotFoundError(
            f"Répertoire de vignettes introuvable : {settings.covers_dir}. "
            "Installez un catalogue complet avant de démarrer l'application."
        )
    if source is None:
        source = create_source(settings)
    templates = Jinja2Templates(directory=PACKAGE_DIR / "templates")

    app = FastAPI(title="myEbooks", version="0.4.0")
    app.state.settings = settings
    app.state.database = database
    app.mount("/static", StaticFiles(directory=PACKAGE_DIR / "static"), name="static")
    app.mount("/covers", StaticFiles(directory=settings.covers_dir), name="covers")

    def library_context(request: Request) -> dict[str, object]:
        query = " ".join(request.query_params.get("q", "").split())[:100]
        authors = database.list_authors()
        requested_author = " ".join(request.query_params.get("author", "").split())[:300]
        selected_author = requested_author if requested_author in set(authors) else ""
        all_books = database.list_books()
        matching_books = (
            [book for book in all_books if book.author == selected_author]
            if selected_author
            else all_books
        )
        if query:
            needle = query.casefold()
            matching_books = [
                book
                for book in matching_books
                if needle
                in " ".join((book.title, book.author or "", book.isbn or "")).casefold()
            ]

        raw_page = request.query_params.get("page", "1")
        valid_page = 1 <= len(raw_page) <= 9 and raw_page.isascii() and raw_page.isdigit()
        requested_page = int(raw_page) if valid_page else 1
        result_count = len(matching_books)
        total_pages = max(1, (result_count + BOOKS_PER_PAGE - 1) // BOOKS_PER_PAGE)
        page = min(max(requested_page, 1), total_pages)
        page_start = (page - 1) * BOOKS_PER_PAGE
        books = matching_books[page_start : page_start + BOOKS_PER_PAGE]

        pagination_path = (
            "/kobo"
            if request.url.path == "/kobo" or _is_kobo_browser(request)
            else "/"
        )

        def page_url(target_page: int) -> str:
            parameters = {"page": str(target_page)}
            if query:
                parameters["q"] = query
            if selected_author:
                parameters["author"] = selected_author
            return f"{pagination_path}?{urlencode(parameters)}"

        return {
            "books": books,
            "total_books": len(all_books),
            "result_count": result_count,
            "query": query,
            "authors": authors,
            "selected_author": selected_author,
            "page": page,
            "total_pages": total_pages,
            "has_previous_page": page > 1,
            "has_next_page": page < total_pages,
            "previous_page": page - 1,
            "next_page": page + 1,
            "previous_page_url": page_url(page - 1) if page > 1 else None,
            "next_page_url": page_url(page + 1) if page < total_pages else None,
            "source_name": source_label(settings),
            "kobo_download_paths": {
                book.id: (
                    f"/kobo/books/{book.id}/"
                    f"{_kobo_url_filename(book.source_name, book.file_format)}"
                )
                for book in books
            },
        }

    def render_library(request: Request, template_name: str) -> HTMLResponse:
        context = library_context(request)
        response = templates.TemplateResponse(
            request=request,
            name=template_name,
            context=context,
        )
        response.headers["Cache-Control"] = "no-store, max-age=0"
        response.headers["Pragma"] = "no-cache"
        return response

    @app.get("/", response_class=HTMLResponse)
    def library(request: Request) -> HTMLResponse:
        template_name = "kobo.html" if _is_kobo_browser(request) else "index.html"
        return render_library(request, template_name)

    @app.get("/kobo", response_class=HTMLResponse, name="kobo_library")
    def kobo_library(request: Request) -> HTMLResponse:
        return render_library(request, "kobo.html")

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

    @app.get("/kobo/covers/{book_id}.png", name="kobo_cover")
    def kobo_cover(book_id: int) -> Response:
        book = database.book_by_id(book_id)
        if book is None or not book.cover_filename:
            raise HTTPException(status_code=404, detail="Couverture introuvable")
        if Path(book.cover_filename).name != book.cover_filename:
            raise HTTPException(status_code=404, detail="Couverture invalide")
        cover_path = settings.covers_dir / book.cover_filename
        if not cover_path.is_file() or cover_path.stat().st_size > 20 * 1024 * 1024:
            raise HTTPException(status_code=404, detail="Couverture introuvable")
        try:
            content = _kobo_cover_png(cover_path)
        except Exception as exc:
            LOGGER.warning("Vignette Kobo impossible pour %s: %s", book.source_name, exc)
            raise HTTPException(status_code=422, detail="Couverture illisible") from exc
        return Response(
            content=content,
            media_type="image/png",
            headers={
                "Content-Length": str(len(content)),
                "Cache-Control": "private, max-age=3600",
                "X-Content-Type-Options": "nosniff",
            },
        )

    def build_download_response(book_id: int, *, legacy_kobo: bool = False) -> StreamingResponse:
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
        disposition = (
            f'attachment; filename="{_kobo_url_filename(filename, book.file_format)}"'
            if legacy_kobo
            else _content_disposition(filename)
        )
        return StreamingResponse(
            _chunks(content),
            media_type=remote_file.mime_type,
            headers={
                "Content-Disposition": disposition,
                "Content-Length": str(len(content)),
                "Cache-Control": "private, no-store",
                "X-Content-Type-Options": "nosniff",
            },
        )

    @app.get("/books/{book_id}/download", name="download_book")
    def download_book(book_id: int) -> StreamingResponse:
        return build_download_response(book_id)

    @app.get(
        "/kobo/books/{book_id}/{filename}",
        name="download_book_kobo",
    )
    def download_book_kobo(book_id: int, filename: str) -> StreamingResponse:
        book = database.book_by_id(book_id)
        if book is None:
            raise HTTPException(status_code=404, detail="Livre introuvable")
        expected_filename = _kobo_url_filename(book.source_name, book.file_format)
        if not secrets.compare_digest(filename, expected_filename):
            raise HTTPException(status_code=404, detail="Lien de téléchargement invalide")
        return build_download_response(book_id, legacy_kobo=True)

    @app.get("/health", response_class=JSONResponse)
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app
