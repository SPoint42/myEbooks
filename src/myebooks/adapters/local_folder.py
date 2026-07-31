from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path

from ..config import Settings
from ..domain import RemoteFile

LOCAL_FILE_ID = re.compile(r"^[0-9a-f]{64}$")
MIME_BY_EXTENSION = {
    ".epub": "application/epub+zip",
    ".pdf": "application/pdf",
}


class LocalFolderSource:
    """Read ebooks from one explicitly configured local directory."""

    def __init__(self, settings: Settings) -> None:
        if settings.local_library_dir is None:
            raise ValueError("Le répertoire local des ebooks est requis")
        self.root = settings.local_library_dir.resolve(strict=True)
        self.max_file_size = settings.max_file_size
        self._paths: dict[str, Path] = {}

    @staticmethod
    def _source_id(relative_path: Path) -> str:
        return hashlib.sha256(relative_path.as_posix().encode("utf-8")).hexdigest()

    def list_files(self) -> list[RemoteFile]:
        files: list[RemoteFile] = []
        paths: dict[str, Path] = {}
        for current_dir, directory_names, file_names in os.walk(self.root, followlinks=False):
            directory_names[:] = sorted(
                name
                for name in directory_names
                if not (Path(current_dir) / name).is_symlink()
            )
            for filename in sorted(file_names):
                path = Path(current_dir) / filename
                suffix = path.suffix.lower()
                if suffix not in MIME_BY_EXTENSION or path.is_symlink():
                    continue
                resolved = path.resolve(strict=True)
                if not resolved.is_relative_to(self.root):
                    continue
                stat = resolved.stat()
                relative_path = resolved.relative_to(self.root)
                source_id = self._source_id(relative_path)
                paths[source_id] = resolved
                files.append(
                    RemoteFile(
                        id=source_id,
                        name=resolved.name,
                        mime_type=MIME_BY_EXTENSION[suffix],
                        modified_time=f"{stat.st_mtime_ns}:{stat.st_size}",
                        size=stat.st_size,
                    )
                )
        self._paths = paths
        return files

    def download(self, remote_file: RemoteFile) -> bytes:
        if not LOCAL_FILE_ID.fullmatch(remote_file.id):
            raise ValueError("Identifiant de fichier local invalide")
        path = self._paths.get(remote_file.id)
        if path is None:
            self.list_files()
            path = self._paths.get(remote_file.id)
        if path is None or path.is_symlink():
            raise FileNotFoundError(remote_file.name)
        resolved = path.resolve(strict=True)
        if not resolved.is_relative_to(self.root):
            raise ValueError("Fichier situé hors de la bibliothèque locale")
        if resolved.stat().st_size > self.max_file_size:
            raise ValueError("Fichier trop volumineux")
        content = resolved.read_bytes()
        if len(content) > self.max_file_size:
            raise ValueError("Fichier trop volumineux")
        return content
