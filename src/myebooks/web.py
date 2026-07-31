from __future__ import annotations

import logging
import secrets
from dataclasses import asdict
from pathlib import Path
from typing import Annotated

from fastapi import BackgroundTasks, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .adapters.google_drive import GoogleDriveSource
from .config import Settings
from .database import LibraryDatabase
from .demo import FakeDriveSource
from .domain import EbookSource
from .indexer import IndexAlreadyRunning, LibraryIndexer

LOGGER = logging.getLogger(__name__)
PACKAGE_DIR = Path(__file__).parent


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
        source = GoogleDriveSource(settings) if settings.source == "google" else FakeDriveSource()
    indexer = LibraryIndexer(settings, database, source)
    templates = Jinja2Templates(directory=PACKAGE_DIR / "templates")

    app = FastAPI(title="myEbooks", version="0.1.0")
    app.state.settings = settings
    app.state.database = database
    app.state.indexer = indexer
    app.mount("/static", StaticFiles(directory=PACKAGE_DIR / "static"), name="static")
    app.mount("/covers", StaticFiles(directory=settings.covers_dir), name="covers")

    @app.get("/", response_class=HTMLResponse)
    def library(request: Request) -> HTMLResponse:
        csrf_token = request.cookies.get("myebooks_csrf") or secrets.token_urlsafe(32)
        response = templates.TemplateResponse(
            request=request,
            name="index.html",
            context={
                "books": database.list_books(),
                "sync": database.latest_sync(),
                "source_name": (
                    "Google Drive" if settings.source == "google" else "Drive de démonstration"
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

    @app.get("/health", response_class=JSONResponse)
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app
