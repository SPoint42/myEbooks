from __future__ import annotations

from .adapters.google_drive import GoogleDriveSource
from .adapters.local_folder import LocalFolderSource
from .adapters.public_google_drive import PublicGoogleDriveSource
from .config import Settings
from .demo import FakeDriveSource
from .domain import EbookSource


def create_source(settings: Settings) -> EbookSource:
    if settings.source == "google":
        return GoogleDriveSource(settings)
    if settings.source == "google_public":
        return PublicGoogleDriveSource(settings)
    if settings.source == "local":
        return LocalFolderSource(settings)
    return FakeDriveSource()


def source_label(settings: Settings) -> str:
    labels = {
        "google_public": "Google Drive public",
        "google": "Google Drive",
        "local": "Dossier local",
        "fake": "Drive de démonstration",
    }
    return labels[settings.source]
