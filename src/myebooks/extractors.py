from __future__ import annotations

import io
import re
import unicodedata
import zipfile
from datetime import UTC, datetime
from pathlib import PurePosixPath

import ebooklib
import pymupdf
from ebooklib import epub

from .config import Settings
from .domain import ExtractedBook

ISBN_LABEL_PATTERN = re.compile(
    r"(?i)\bISBN(?:-1[03])?\b[^0-9X]{0,12}((?:97[89][\s-]?)?(?:\d[\s-]?){9}[\dX])"
)
YEAR_PATTERN = re.compile(r"\b(1[5-9]\d{2}|20\d{2})\b")
SAFE_IMAGE_TYPES = {
    "image/jpeg": ("jpg", (b"\xff\xd8\xff",)),
    "image/png": ("png", (b"\x89PNG\r\n\x1a\n",)),
    "image/gif": ("gif", (b"GIF87a", b"GIF89a")),
    "image/webp": ("webp", (b"RIFF",)),
}


class EbookParseError(ValueError):
    """Raised when an ebook cannot be parsed safely."""


def _clean(value: object, maximum: int = 500) -> str | None:
    if value is None:
        return None
    text = unicodedata.normalize("NFKC", str(value))
    text = " ".join(text.replace("\x00", " ").split())
    return text[:maximum] or None


def _fallback_title(filename: str) -> str:
    stem = filename.rsplit(".", 1)[0].replace("_", " ").replace("-", " ")
    return _clean(stem, 300) or "Sans titre"


def _valid_isbn(candidate: str) -> bool:
    normalized = re.sub(r"[^0-9X]", "", candidate.upper())
    if len(normalized) == 10:
        total = sum(
            (10 - index) * (10 if char == "X" else int(char))
            for index, char in enumerate(normalized)
        )
        return total % 11 == 0
    if len(normalized) == 13 and normalized.isdigit():
        total = sum(
            int(char) * (1 if index % 2 == 0 else 3)
            for index, char in enumerate(normalized[:12])
        )
        return (10 - total % 10) % 10 == int(normalized[-1])
    return False


def extract_isbn(text: str) -> str | None:
    for match in ISBN_LABEL_PATTERN.finditer(text):
        normalized = re.sub(r"[^0-9X]", "", match.group(1).upper())
        if _valid_isbn(normalized):
            return normalized
    return None


def _extract_year(text: str | None) -> int | None:
    if not text:
        return None
    current_year = datetime.now(UTC).year + 1
    pdf_date = re.search(r"D:(\d{4})", text)
    if pdf_date and 1500 <= int(pdf_date.group(1)) <= current_year:
        return int(pdf_date.group(1))
    for match in YEAR_PATTERN.finditer(text):
        year = int(match.group(1))
        if year <= current_year:
            return year
    return None


def _safe_cover(content: bytes, media_type: str | None) -> tuple[bytes | None, str | None]:
    if not content or len(content) > 20 * 1024 * 1024 or media_type not in SAFE_IMAGE_TYPES:
        return None, None
    extension, signatures = SAFE_IMAGE_TYPES[media_type]
    if extension == "webp":
        valid = content.startswith(b"RIFF") and content[8:12] == b"WEBP"
    else:
        valid = any(content.startswith(signature) for signature in signatures)
    return (content, extension) if valid else (None, None)


def _validate_epub_archive(data: bytes, settings: Settings) -> None:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            entries = archive.infolist()
            if len(entries) > settings.max_epub_entries:
                raise EbookParseError("EPUB refusé : trop de fichiers dans l'archive")

            expanded_size = 0
            for entry in entries:
                path = PurePosixPath(entry.filename)
                if path.is_absolute() or ".." in path.parts or "\\" in entry.filename:
                    raise EbookParseError("EPUB refusé : chemin interne dangereux")
                if entry.flag_bits & 0x1:
                    raise EbookParseError("EPUB chiffré non pris en charge")
                expanded_size += entry.file_size
                if expanded_size > settings.max_epub_expanded_size:
                    raise EbookParseError("EPUB refusé : archive décompressée trop volumineuse")
                if (
                    entry.compress_size
                    and entry.file_size > 1_000_000
                    and entry.file_size / entry.compress_size > 1_000
                ):
                    raise EbookParseError("EPUB refusé : taux de compression suspect")

                suffix = path.suffix.lower()
                if suffix in {".xml", ".opf", ".ncx"} and entry.file_size <= 2_000_000:
                    header = archive.read(entry)[:2_000_000].upper()
                    if b"<!ENTITY" in header or (b"<!DOCTYPE" in header and b"SYSTEM" in header):
                        raise EbookParseError("EPUB refusé : entités XML externes")
    except zipfile.BadZipFile as exc:
        raise EbookParseError("EPUB invalide") from exc


def extract_epub(filename: str, data: bytes, settings: Settings) -> ExtractedBook:
    _validate_epub_archive(data, settings)
    try:
        book = epub.read_epub(io.BytesIO(data), options={"ignore_ncx": True})
    except Exception as exc:
        raise EbookParseError("Impossible de lire les métadonnées EPUB") from exc

    def dc(name: str) -> list[tuple[object, dict[str, str]]]:
        return book.get_metadata("DC", name)

    titles = dc("title")
    creators = dc("creator")
    dates = dc("date")
    identifiers = dc("identifier")
    title = _clean(titles[0][0], 300) if titles else None
    authors = [_clean(value, 200) for value, _attributes in creators]
    author = ", ".join(value for value in authors if value) or None
    date = _clean(dates[0][0]) if dates else None

    isbn = None
    for value, attributes in identifiers:
        identifier = f"{value} {' '.join(f'{key}={item}' for key, item in attributes.items())}"
        normalized = re.sub(r"[^0-9X]", "", str(value).upper())
        if "isbn" in identifier.lower() and _valid_isbn(normalized):
            isbn = normalized
            break
        candidate = extract_isbn(identifier)
        if candidate:
            isbn = candidate
            break

    cover_item = None
    for _value, attributes in book.get_metadata("OPF", "cover"):
        item_id = attributes.get("content")
        if item_id:
            cover_item = book.get_item_with_id(item_id)
            if cover_item:
                break
    if cover_item is None:
        for item in book.get_items_of_type(ebooklib.ITEM_COVER):
            cover_item = item
            break
    if cover_item is None:
        for item in book.get_items_of_type(ebooklib.ITEM_IMAGE):
            marker = f"{item.get_id()} {item.get_name()}".lower()
            if "cover" in marker:
                cover_item = item
                break

    cover, cover_extension = (None, None)
    if cover_item is not None:
        cover, cover_extension = _safe_cover(cover_item.get_content(), cover_item.media_type)

    return ExtractedBook(
        title=title or _fallback_title(filename),
        author=author,
        publication_year=_extract_year(date),
        isbn=isbn,
        cover=cover,
        cover_extension=cover_extension,
    )


def extract_pdf(filename: str, data: bytes) -> ExtractedBook:
    try:
        document = pymupdf.open(stream=data, filetype="pdf")
    except Exception as exc:
        raise EbookParseError("PDF invalide") from exc

    with document:
        if document.page_count < 1:
            raise EbookParseError("PDF sans page")
        metadata = document.metadata or {}
        title = _clean(metadata.get("title"), 300)
        if title and title.lower() in {"untitled", "sans titre"}:
            title = None
        author = _clean(metadata.get("author"), 300)
        date_text = " ".join(
            str(metadata.get(key, "")) for key in ("creationDate", "modDate", "subject")
        )

        sample_parts: list[str] = []
        for page_index in range(min(3, document.page_count)):
            try:
                sample_parts.append(document[page_index].get_text("text")[:50_000])
            except Exception:
                continue
        sample = "\n".join(sample_parts)

        cover = None
        try:
            page = document[0]
            longest_side = max(float(page.rect.width), float(page.rect.height), 1.0)
            scale = min(1.5, 900.0 / longest_side)
            pixmap = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False)
            cover = pixmap.tobytes("png")
        except Exception:
            pass

    return ExtractedBook(
        title=title or _fallback_title(filename),
        author=author,
        publication_year=_extract_year(date_text),
        isbn=extract_isbn(sample),
        cover=cover,
        cover_extension="png" if cover else None,
    )


def extract_book(filename: str, data: bytes, settings: Settings) -> ExtractedBook:
    extension = filename.rsplit(".", 1)[-1].lower()
    if extension == "epub":
        return extract_epub(filename, data, settings)
    if extension == "pdf":
        return extract_pdf(filename, data)
    raise EbookParseError("Format non pris en charge")
