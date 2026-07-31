from __future__ import annotations

import io
import logging
import re
from pathlib import PurePosixPath

import gdown
import httpx
from gdown.exceptions import FileURLRetrievalError

from ..config import Settings
from ..domain import RemoteFile

DRIVE_FILE_ID = re.compile(r"^[A-Za-z0-9_-]{20,}$")
DIRECT_DOWNLOAD_URL = "https://drive.usercontent.google.com/download"
LOGGER = logging.getLogger("uvicorn.error.myebooks.google_drive")
MIME_BY_EXTENSION = {
    ".epub": "application/epub+zip",
}


class PublicGoogleDriveSource:
    """Read a public Google Drive folder without a Google account."""

    def __init__(self, settings: Settings) -> None:
        if not settings.google_drive_public_url:
            raise ValueError("Le lien du dossier Google Drive public est requis")
        self.folder_url = settings.google_drive_public_url
        self.max_file_size = settings.max_file_size

    def list_files(self) -> list[RemoteFile]:
        entries = gdown.download_folder(
            url=self.folder_url,
            quiet=True,
            use_cookies=False,
            skip_download=True,
        )
        files: list[RemoteFile] = []
        for entry in entries:
            suffix = PurePosixPath(entry.path).suffix.lower()
            if suffix not in MIME_BY_EXTENSION or not DRIVE_FILE_ID.fullmatch(entry.id):
                continue
            files.append(
                RemoteFile(
                    id=entry.id,
                    name=PurePosixPath(entry.path).name,
                    mime_type=MIME_BY_EXTENSION[suffix],
                    # Le listing public n'expose ni checksum ni date de modification.
                    # L'option « Tout réanalyser » permet de forcer une actualisation.
                    modified_time="public-link-v1",
                )
            )
        return files

    def _validate_content(self, remote_file: RemoteFile, content: bytes) -> bytes:
        if len(content) > self.max_file_size:
            raise ValueError("Fichier trop volumineux")
        if not content.startswith(b"PK"):
            raise ValueError("Le contenu téléchargé n'est pas un EPUB valide")
        return content

    def _download_with_gdown(self, remote_file: RemoteFile) -> bytes:
        target = io.BytesIO()

        def enforce_size(downloaded: int, total: int | None) -> None:
            if total is not None and total > self.max_file_size:
                raise ValueError("Fichier trop volumineux")
            if downloaded > self.max_file_size:
                raise ValueError("Téléchargement interrompu : taille maximale dépassée")

        result = gdown.download(
            id=remote_file.id,
            output=target,
            quiet=True,
            use_cookies=False,
            progress=enforce_size,
        )
        if result is None:
            raise FileNotFoundError(remote_file.name)
        return self._validate_content(remote_file, target.getvalue())

    def _download_direct(self, remote_file: RemoteFile) -> bytes:
        timeout = httpx.Timeout(300, connect=15)
        with httpx.stream(
            "GET",
            DIRECT_DOWNLOAD_URL,
            params={"id": remote_file.id, "export": "download", "confirm": "t"},
            follow_redirects=False,
            timeout=timeout,
        ) as response:
            response.raise_for_status()
            content_length = response.headers.get("content-length")
            if content_length and int(content_length) > self.max_file_size:
                raise ValueError("Fichier trop volumineux")
            content = bytearray()
            for chunk in response.iter_bytes(chunk_size=512 * 1024):
                content.extend(chunk)
                if len(content) > self.max_file_size:
                    raise ValueError("Téléchargement interrompu : taille maximale dépassée")
        return self._validate_content(remote_file, bytes(content))

    def download(self, remote_file: RemoteFile) -> bytes:
        if not DRIVE_FILE_ID.fullmatch(remote_file.id):
            raise ValueError("Identifiant Google Drive invalide")
        if (
            not remote_file.name.lower().endswith(".epub")
            or remote_file.mime_type != "application/epub+zip"
        ):
            raise ValueError("Seuls les fichiers EPUB peuvent être téléchargés")
        try:
            return self._download_with_gdown(remote_file)
        except FileURLRetrievalError:
            LOGGER.info(
                "gdown indisponible pour %s ; essai du téléchargement public direct",
                remote_file.name,
            )
            try:
                return self._download_direct(remote_file)
            except Exception as direct_exc:
                raise FileNotFoundError(
                    f"Téléchargement public impossible pour {remote_file.name}"
                ) from direct_exc
