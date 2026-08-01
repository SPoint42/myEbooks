from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import pytest
from gdown.exceptions import FileURLRetrievalError

from myebooks.adapters.public_google_drive import PublicGoogleDriveSource
from myebooks.demo import demo_pdf
from myebooks.domain import RemoteFile

PUBLIC_URL = "https://drive.google.com/drive/folders/1AbCdEfGhIjKlMnOpQrStUvWx"


def public_source(settings, extensions=frozenset({"epub"})):
    return PublicGoogleDriveSource(
        replace(
            settings,
            source="google_public",
            google_drive_public_url=PUBLIC_URL,
            index_extensions=extensions,
        )
    )


def test_public_folder_lists_only_epub(monkeypatch, settings):
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

    assert [item.name for item in files] == ["novel.epub"]
    assert {item.mime_type for item in files} == {"application/epub+zip"}
    assert all(item.modified_time == "public-link-v1" for item in files)


def test_public_file_download_is_bounded(monkeypatch, settings):
    source = public_source(settings)
    remote_file = RemoteFile(
        id="1EpubFileIdAbCdEfGhIjKlM",
        name="book.epub",
        mime_type="application/epub+zip",
        modified_time="public-link-v1",
    )

    def fake_download(*, output, progress, **_arguments):
        content = b"PK\x03\x04a public ebook"
        output.write(content)
        progress(len(content), len(content))
        return output

    monkeypatch.setattr(
        "myebooks.adapters.public_google_drive.gdown.download",
        fake_download,
    )

    assert source.download(remote_file) == b"PK\x03\x04a public ebook"


def test_public_file_download_accepts_valid_pdf(monkeypatch, settings):
    source = public_source(settings, frozenset({"pdf"}))
    remote_file = RemoteFile(
        id="1PdfFileIdAbCdEfGhIjKlMn",
        name="book.pdf",
        mime_type="application/pdf",
        modified_time="public-link-v1",
    )

    content = demo_pdf()

    def fake_download(*, output, progress, **_arguments):
        output.write(content)
        progress(len(content), len(content))
        return output

    monkeypatch.setattr(
        "myebooks.adapters.public_google_drive.gdown.download",
        fake_download,
    )

    assert source.download(remote_file) == content


def test_public_file_download_falls_back_to_googleusercontent(monkeypatch, settings):
    source = public_source(settings)
    remote_file = RemoteFile(
        id="178bd3b5nWYGhj9onNJgGDvPmiN0sEjq6",
        name="Leon-l-Africain.epub",
        mime_type="application/epub+zip",
        modified_time="public-link-v1",
    )
    request = {}

    def failed_gdown(**_arguments):
        raise FileURLRetrievalError("Cannot retrieve the public link")

    class FakeResponse:
        headers = {"content-length": "16"}

        def __enter__(self):
            return self

        def __exit__(self, *_arguments):
            return None

        def raise_for_status(self):
            return None

        def iter_bytes(self, *, chunk_size):
            assert chunk_size == 512 * 1024
            yield b"PK\x03\x04fake-epub"

    def fake_stream(method, url, **arguments):
        request.update({"method": method, "url": url, **arguments})
        return FakeResponse()

    monkeypatch.setattr("myebooks.adapters.public_google_drive.gdown.download", failed_gdown)
    monkeypatch.setattr("myebooks.adapters.public_google_drive.httpx.stream", fake_stream)

    content = source.download(remote_file)

    assert content == b"PK\x03\x04fake-epub"
    assert request["url"] == "https://drive.usercontent.google.com/download"
    assert request["params"]["id"] == remote_file.id
    assert request["follow_redirects"] is False


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
