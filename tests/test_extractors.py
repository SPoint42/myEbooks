from __future__ import annotations

import io
import zipfile

import pytest

from myebooks.demo import demo_epub, demo_pdf
from myebooks.extractors import EbookParseError, extract_epub, extract_isbn, extract_pdf


def test_extract_pdf_metadata_and_first_page_cover():
    book = extract_pdf("fallback.pdf", demo_pdf())

    assert book.title == "The Pragmatic Programmer"
    assert book.author == "David Thomas, Andrew Hunt"
    assert book.publication_year == 2019
    assert book.isbn == "9780135957059"
    assert book.cover is not None
    assert book.cover.startswith(b"\x89PNG")
    assert book.cover_extension == "png"


def test_extract_epub_metadata_and_embedded_cover(settings):
    book = extract_epub("fallback.epub", demo_epub(), settings)

    assert book.title == "Clean Code"
    assert book.author == "Robert C. Martin"
    assert book.publication_year == 2008
    assert book.isbn == "9780132350884"
    assert book.cover is not None
    assert book.cover_extension == "png"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("ISBN 978-0-13-595705-9", "9780135957059"),
        ("ISBN: 0-13-235088-2", "0132350882"),
        ("ISBN 978-0-00-000000-0", None),
        ("9780135957059 sans libellé", None),
    ],
)
def test_isbn_is_labelled_and_checksum_valid(text, expected):
    assert extract_isbn(text) == expected


def test_epub_rejects_path_traversal(settings):
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w") as archive:
        archive.writestr("mimetype", "application/epub+zip")
        archive.writestr("../outside.opf", "unsafe")

    with pytest.raises(EbookParseError, match="chemin interne dangereux"):
        extract_epub("unsafe.epub", payload.getvalue(), settings)
