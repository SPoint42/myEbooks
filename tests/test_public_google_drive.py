from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import pytest

from myebooks.adapters.public_google_drive import PublicGoogleDriveSource
from myebooks.domain import RemoteFile

PUBLIC_URL = "https://drive.google.com/drive/folders/1AbCdEfGhIjKlMnOpQrStUvWx"


def public_source(settings):
    return PublicGoogleDriveSource(
        replace(settings, source="google_public", google_drive_public_url=PUBLIC_URL)
    )


def test_public_folder_lists_only_pdf_and_epub(monkeypatch, settings):
    entries = [
        SimpleNamespace(
            id="1PdfFileIdAbCdEfGhIjKlMn",
            path="Technique/secure-coding.pdf",
        ),
        SimpleNamespace(
            id="1EpubFileIdAbCdEfGhIjKlM",
            path="Romans/novel.epub",
        ),
        SimpleNamespace(id="1TextFileIdAbCdEfGhIjKlMn", path="notes.txt"),
    ]
    monkeypatch.setattr(
        "myebooks.adapters.public_google_drive.gdown.download_folder",
        lambda **_arguments: entries,
    )

    files = public_source(settings).list_files()

    assert [item.name for item in files] == ["secure-coding.pdf", "novel.epub"]
    assert {item.mime_type for item in files} == {"application/pdf", "application/epub+zip"}
    assert all(item.modified_time == "public-link-v1" for item in files)


def test_public_file_download_is_bounded(monkeypatch, settings):
    source = public_source(settings)
    remote_file = RemoteFile(
        id="1PdfFileIdAbCdEfGhIjKlMn",
        name="book.pdf",
        mime_type="application/pdf",
        modified_time="public-link-v1",
    )

    def fake_download(*, output, progress, **_arguments):
        content = b"a public ebook"
        output.write(content)
        progress(len(content), len(content))
        return output

    monkeypatch.setattr(
        "myebooks.adapters.public_google_drive.gdown.download",
        fake_download,
    )

    assert source.download(remote_file) == b"a public ebook"


def test_public_file_download_rejects_unknown_identifier(settings):
    source = public_source(settings)
    remote_file = RemoteFile(
        id="../not-a-drive-id",
        name="book.pdf",
        mime_type="application/pdf",
        modified_time="public-link-v1",
    )

    with pytest.raises(ValueError, match="Identifiant Google Drive invalide"):
        source.download(remote_file)
