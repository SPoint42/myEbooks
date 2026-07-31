from __future__ import annotations

import hashlib
import io
import struct
import zlib

import pymupdf
from ebooklib import epub

from .domain import RemoteFile


def _png(width: int = 600, height: int = 900) -> bytes:
    row = b"\x00" + bytes((29, 78, 216)) * width
    raw = row * height

    def chunk(kind: bytes, content: bytes) -> bytes:
        return struct.pack(">I", len(content)) + kind + content + struct.pack(
            ">I", zlib.crc32(kind + content) & 0xFFFFFFFF
        )

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw, 9))
        + chunk(b"IEND", b"")
    )


def demo_epub() -> bytes:
    book = epub.EpubBook()
    book.set_identifier("urn:isbn:9780132350884")
    book.set_title("Clean Code")
    book.set_language("fr")
    book.add_author("Robert C. Martin")
    book.add_metadata("DC", "date", "2008-08-01")
    book.set_cover("cover.png", _png())
    chapter = epub.EpubHtml(title="Introduction", file_name="intro.xhtml", lang="fr")
    chapter.content = "<h1>Introduction</h1><p>Un livre de démonstration.</p>"
    book.add_item(chapter)
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.toc = (chapter,)
    book.spine = ["nav", chapter]
    output = io.BytesIO()
    epub.write_epub(output, book, {"raise_exceptions": True})
    return output.getvalue()


def demo_pdf() -> bytes:
    document = pymupdf.open()
    page = document.new_page(width=420, height=640)
    page.draw_rect(page.rect, color=(0.05, 0.22, 0.18), fill=(0.05, 0.22, 0.18))
    page.insert_text((45, 150), "The Pragmatic Programmer", fontsize=24, color=(1, 1, 1))
    page.insert_text((45, 200), "David Thomas, Andrew Hunt", fontsize=14, color=(0.8, 0.95, 0.9))
    page.insert_text((45, 560), "ISBN 978-0-13-595705-9", fontsize=11, color=(1, 1, 1))
    document.set_metadata(
        {
            "title": "The Pragmatic Programmer",
            "author": "David Thomas, Andrew Hunt",
            "creationDate": "D:20190913200000+00'00'",
        }
    )
    content = document.tobytes()
    document.close()
    return content


class FakeDriveSource:
    def __init__(self) -> None:
        self._files = {
            "demo-epub": ("clean-code.epub", "application/epub+zip", demo_epub()),
            "demo-pdf": ("pragmatic-programmer.pdf", "application/pdf", demo_pdf()),
        }

    def list_files(self) -> list[RemoteFile]:
        result = []
        for source_id, (name, mime_type, content) in self._files.items():
            result.append(
                RemoteFile(
                    id=source_id,
                    name=name,
                    mime_type=mime_type,
                    modified_time="2026-01-01T00:00:00Z",
                    checksum=hashlib.sha256(content).hexdigest(),
                    size=len(content),
                )
            )
        return result

    def download(self, remote_file: RemoteFile) -> bytes:
        try:
            return self._files[remote_file.id][2]
        except KeyError as exc:
            raise FileNotFoundError(remote_file.id) from exc
