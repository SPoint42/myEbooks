from __future__ import annotations

import io
import re
from pathlib import PurePosixPath

import gdown

from ..config import Settings
from ..domain import RemoteFile

DRIVE_FILE_ID = re.compile(r"^[A-Za-z0-9_-]{20,}$")
MIME_BY_EXTENSION = {
    ".epub": "application/epub+zip",
    ".pdf": "application/pdf",
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

    def download(self, remote_file: RemoteFile) -> bytes:
        if not DRIVE_FILE_ID.fullmatch(remote_file.id):
            raise ValueError("Identifiant Google Drive invalide")
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
        content = target.getvalue()
        if len(content) > self.max_file_size:
            raise ValueError("Fichier trop volumineux")
        return content
