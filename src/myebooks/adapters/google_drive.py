from __future__ import annotations

import io

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

from ..config import Settings
from ..domain import RemoteFile

DRIVE_READONLY_SCOPE = "https://www.googleapis.com/auth/drive.readonly"
FOLDER_MIME_TYPE = "application/vnd.google-apps.folder"
EBOOK_MIME_TYPES = {"application/pdf", "application/epub+zip"}


class GoogleDriveSource:
    def __init__(self, settings: Settings) -> None:
        if settings.google_service_account_file is None:
            raise ValueError("Le fichier du compte de service Google est requis")
        credentials = service_account.Credentials.from_service_account_file(
            str(settings.google_service_account_file), scopes=[DRIVE_READONLY_SCOPE]
        )
        self.service = build("drive", "v3", credentials=credentials, cache_discovery=False)
        self.drive_id = settings.google_drive_id
        self.folder_id = settings.google_drive_folder_id
        self.max_file_size = settings.max_file_size

    @staticmethod
    def _is_ebook(item: dict[str, object]) -> bool:
        name = str(item.get("name", "")).lower()
        return str(item.get("mimeType", "")) in EBOOK_MIME_TYPES or name.endswith((".pdf", ".epub"))

    @staticmethod
    def _remote_file(item: dict[str, object]) -> RemoteFile:
        raw_size = item.get("size")
        return RemoteFile(
            id=str(item["id"]),
            name=str(item["name"]),
            mime_type=str(item.get("mimeType", "application/octet-stream")),
            modified_time=str(item.get("modifiedTime", "")),
            checksum=str(item["md5Checksum"]) if item.get("md5Checksum") else None,
            size=int(str(raw_size)) if raw_size is not None else None,
        )

    def _list_query(self, query: str) -> list[dict[str, object]]:
        items: list[dict[str, object]] = []
        page_token = None
        while True:
            arguments: dict[str, object] = {
                "q": query,
                "spaces": "drive",
                "fields": "nextPageToken, files(id,name,mimeType,modifiedTime,md5Checksum,size)",
                "pageSize": 1000,
                "pageToken": page_token,
                "supportsAllDrives": True,
                "includeItemsFromAllDrives": True,
            }
            if self.drive_id:
                arguments.update({"corpora": "drive", "driveId": self.drive_id})
            response = self.service.files().list(**arguments).execute()
            items.extend(response.get("files", []))
            page_token = response.get("nextPageToken")
            if not page_token:
                return items

    def list_files(self) -> list[RemoteFile]:
        if not self.folder_id:
            items = self._list_query("trashed = false")
            return [self._remote_file(item) for item in items if self._is_ebook(item)]

        discovered: list[RemoteFile] = []
        folders = [self.folder_id]
        visited: set[str] = set()
        while folders:
            folder_id = folders.pop()
            if folder_id in visited:
                continue
            visited.add(folder_id)
            safe_folder_id = folder_id.replace("\\", "\\\\").replace("'", "\\'")
            for item in self._list_query(f"'{safe_folder_id}' in parents and trashed = false"):
                if item.get("mimeType") == FOLDER_MIME_TYPE:
                    folders.append(str(item["id"]))
                elif self._is_ebook(item):
                    discovered.append(self._remote_file(item))
        return discovered

    def download(self, remote_file: RemoteFile) -> bytes:
        if remote_file.size is not None and remote_file.size > self.max_file_size:
            raise ValueError(f"Fichier trop volumineux ({remote_file.size} octets)")
        request = self.service.files().get_media(fileId=remote_file.id, supportsAllDrives=True)
        target = io.BytesIO()
        downloader = MediaIoBaseDownload(target, request, chunksize=4 * 1024 * 1024)
        done = False
        while not done:
            _status, done = downloader.next_chunk()
            if target.tell() > self.max_file_size:
                raise ValueError("Téléchargement interrompu : taille maximale dépassée")
        return target.getvalue()
