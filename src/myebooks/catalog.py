from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import tarfile
import tempfile
from contextlib import closing
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

from .config import Settings
from .database import LibraryDatabase
from .domain import EbookSource, IndexResult
from .indexer import ALLOWED_COVER_EXTENSIONS, LibraryIndexer
from .sources import source_label

CATALOG_SCHEMA_VERSION = 1
MAX_ARCHIVE_FILES = 5_000
MAX_ARCHIVE_SIZE = 1024 * 1024 * 1024
CATALOG_TAG = re.compile(r"^catalog-\d{8}T\d{6}Z$")
CHECKSUM_LINE = re.compile(r"^([0-9a-f]{64})  ([A-Za-z0-9._-]+)$")
COVER_FILENAME = re.compile(r"^[0-9a-f]{64}\.(?:gif|jpg|png|webp)$")
GIT_COMMIT = re.compile(r"^[0-9a-f]{40,64}$")


@dataclass(frozen=True, slots=True)
class CatalogArtifact:
    version: str
    archive_path: Path
    checksum_path: Path
    staged_catalog: Path
    result: IndexResult
    book_count: int
    cover_count: int


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def index_library(settings: Settings, source: EbookSource, *, force: bool = False) -> IndexResult:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.covers_dir.mkdir(parents=True, exist_ok=True)
    database = LibraryDatabase(settings.database_path)
    database.initialize()
    result = LibraryIndexer(settings, database, source).run(force=force)
    database.prepare_for_read_only()
    return result


def _export_database(source: Path, destination: Path) -> None:
    if not source.is_file():
        raise FileNotFoundError(f"Base SQLite absente : {source}")
    with closing(sqlite3.connect(source)) as source_connection, closing(
        sqlite3.connect(destination)
    ) as destination_connection:
        source_connection.backup(destination_connection)
        destination_connection.execute("PRAGMA journal_mode = DELETE")
        destination_connection.execute("VACUUM")
        integrity = destination_connection.execute("PRAGMA quick_check").fetchone()
        if integrity is None or integrity[0] != "ok":
            raise RuntimeError("La copie SQLite destinée au déploiement est corrompue")


def _copy_referenced_covers(settings: Settings, database_path: Path, destination: Path) -> int:
    destination.mkdir(parents=True, exist_ok=True)
    database = LibraryDatabase(database_path, read_only=True)
    database.validate_catalog()
    filenames = sorted(
        {book.cover_filename for book in database.list_books() if book.cover_filename}
    )
    for filename in filenames:
        if Path(filename).name != filename:
            raise RuntimeError(f"Nom de vignette invalide dans SQLite : {filename}")
        extension = Path(filename).suffix.lower().lstrip(".")
        if extension not in ALLOWED_COVER_EXTENSIONS:
            raise RuntimeError(f"Extension de vignette invalide dans SQLite : {filename}")
        source = settings.covers_dir / filename
        if not source.is_file():
            raise FileNotFoundError(f"Vignette référencée mais absente : {source}")
        shutil.copyfile(source, destination / filename)
    return len(filenames)


def _replace_directory(source: Path, destination: Path) -> None:
    destination_parent = destination.parent.resolve()
    destination_resolved = destination.resolve()
    if destination_resolved == Path(destination_resolved.anchor) or destination.name != "catalog":
        raise ValueError("Le répertoire de staging doit se terminer par deploy/catalog")

    destination_parent.mkdir(parents=True, exist_ok=True)
    backup = destination_parent / f".{destination.name}.backup"
    if backup.exists():
        shutil.rmtree(backup)
    if destination.exists():
        destination.rename(backup)
    try:
        source.rename(destination)
    except Exception:
        if backup.exists() and not destination.exists():
            backup.rename(destination)
        raise
    if backup.exists():
        shutil.rmtree(backup)


def _write_archive(catalog_dir: Path, archive_path: Path) -> None:
    temporary_archive = archive_path.with_suffix(f"{archive_path.suffix}.tmp")
    with tarfile.open(temporary_archive, "w:gz") as archive:
        for name in ("manifest.json", "myebooks.sqlite3"):
            archive.add(catalog_dir / name, arcname=name, recursive=False)
        for cover in sorted((catalog_dir / "covers").iterdir()):
            if cover.is_file():
                archive.add(cover, arcname=f"covers/{cover.name}", recursive=False)
    os.replace(temporary_archive, archive_path)


def build_catalog_artifact(
    settings: Settings,
    source: EbookSource,
    *,
    output_dir: Path,
    staged_catalog: Path,
    force: bool = False,
    generated_at: datetime | None = None,
) -> CatalogArtifact:
    result = index_library(settings, source, force=force)
    generated_at = generated_at or datetime.now(UTC)
    version = generated_at.strftime("%Y%m%dT%H%M%SZ")
    output_dir.mkdir(parents=True, exist_ok=True)
    staged_catalog.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(
        prefix=".myebooks-catalog-", dir=staged_catalog.parent
    ) as temporary:
        temporary_root = Path(temporary)
        catalog_dir = temporary_root / "catalog"
        catalog_dir.mkdir()
        database_path = catalog_dir / "myebooks.sqlite3"
        _export_database(settings.database_path, database_path)
        cover_count = _copy_referenced_covers(settings, database_path, catalog_dir / "covers")
        book_count = len(LibraryDatabase(database_path, read_only=True).list_books())
        database_hash = _sha256(database_path)
        manifest = {
            "schema_version": CATALOG_SCHEMA_VERSION,
            "version": version,
            "generated_at": generated_at.isoformat(),
            "source": source_label(settings),
            "book_count": book_count,
            "cover_count": cover_count,
            "database_sha256": database_hash,
            "index_result": asdict(result),
        }
        (catalog_dir / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        (catalog_dir / ".gitkeep").touch()
        _replace_directory(catalog_dir, staged_catalog)

    archive_path = output_dir / f"myebooks-catalog-{version}.tar.gz"
    _write_archive(staged_catalog, archive_path)
    checksum = _sha256(archive_path)
    checksum_path = output_dir / f"{archive_path.name}.sha256"
    checksum_path.write_text(f"{checksum}  {archive_path.name}\n", encoding="ascii")
    return CatalogArtifact(
        version=version,
        archive_path=archive_path,
        checksum_path=checksum_path,
        staged_catalog=staged_catalog,
        result=result,
        book_count=book_count,
        cover_count=cover_count,
    )


def publish_catalog_release(artifact: CatalogArtifact, *, project_dir: Path) -> str:
    tag = f"catalog-{artifact.version}"
    if not CATALOG_TAG.fullmatch(tag):
        raise ValueError("Tag de catalogue invalide")
    if shutil.which("gh") is None:
        raise RuntimeError("La commande gh est requise pour publier le catalogue")
    worktree_status = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=project_dir,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if worktree_status:
        raise RuntimeError(
            "Le dépôt contient des changements non commités ; "
            "commitez le code avant de publier un catalogue."
        )
    target = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=project_dir,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if not GIT_COMMIT.fullmatch(target):
        raise RuntimeError("Impossible de déterminer le commit Git à associer au catalogue")

    notes = (
        "Catalogue myEbooks généré localement.\n\n"
        f"- Livres disponibles : {artifact.book_count}\n"
        f"- Vignettes : {artifact.cover_count}\n"
        "- Contenu : métadonnées SQLite et vignettes, sans fichier EPUB source."
    )
    subprocess.run(
        [
            "gh",
            "release",
            "create",
            tag,
            str(artifact.archive_path),
            str(artifact.checksum_path),
            "--target",
            target,
            "--title",
            f"Catalogue myEbooks {artifact.version}",
            "--notes",
            notes,
            "--prerelease",
        ],
        cwd=project_dir,
        check=True,
    )
    return tag


def _safe_archive_path(name: str) -> PurePosixPath:
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise ValueError(f"Chemin interdit dans l'archive : {name}")
    allowed_file = path.as_posix() in {"manifest.json", "myebooks.sqlite3"}
    allowed_cover = (
        len(path.parts) == 2
        and path.parts[0] == "covers"
        and COVER_FILENAME.fullmatch(path.parts[1]) is not None
    )
    if not (allowed_file or allowed_cover):
        raise ValueError(f"Fichier inattendu dans l'archive : {name}")
    return path


def install_catalog_archive(
    archive_path: Path,
    checksum_path: Path,
    *,
    staged_catalog: Path,
) -> None:
    checksum_match = CHECKSUM_LINE.fullmatch(checksum_path.read_text(encoding="ascii").strip())
    if checksum_match is None or checksum_match.group(2) != archive_path.name:
        raise ValueError("Fichier de checksum invalide")
    if _sha256(archive_path) != checksum_match.group(1):
        raise ValueError("Le checksum SHA-256 du catalogue ne correspond pas")

    staged_catalog.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix=".myebooks-install-", dir=staged_catalog.parent
    ) as temporary:
        extracted = Path(temporary) / "catalog"
        extracted.mkdir()
        total_size = 0
        seen: set[PurePosixPath] = set()
        with tarfile.open(archive_path, "r:gz") as archive:
            members = archive.getmembers()
            if len(members) > MAX_ARCHIVE_FILES:
                raise ValueError("Le catalogue contient trop de fichiers")
            for member in members:
                if not member.isfile():
                    raise ValueError(f"Entrée non régulière interdite : {member.name}")
                relative_path = _safe_archive_path(member.name)
                if relative_path in seen:
                    raise ValueError(f"Entrée dupliquée dans l'archive : {member.name}")
                seen.add(relative_path)
                total_size += member.size
                if total_size > MAX_ARCHIVE_SIZE:
                    raise ValueError("Le catalogue décompressé dépasse la taille maximale")
                extracted_file = archive.extractfile(member)
                if extracted_file is None:
                    raise ValueError(f"Entrée illisible dans l'archive : {member.name}")
                destination = extracted.joinpath(*relative_path.parts)
                destination.parent.mkdir(parents=True, exist_ok=True)
                with extracted_file, destination.open("xb") as output:
                    shutil.copyfileobj(extracted_file, output)

        required = {PurePosixPath("manifest.json"), PurePosixPath("myebooks.sqlite3")}
        if not required.issubset(seen):
            raise ValueError("Le catalogue ne contient pas tous les fichiers requis")
        manifest = json.loads((extracted / "manifest.json").read_text(encoding="utf-8"))
        if manifest.get("schema_version") != CATALOG_SCHEMA_VERSION:
            raise ValueError("Version de catalogue incompatible")
        if manifest.get("database_sha256") != _sha256(extracted / "myebooks.sqlite3"):
            raise ValueError("Le checksum de la base SQLite ne correspond pas au manifeste")
        LibraryDatabase(extracted / "myebooks.sqlite3", read_only=True).validate_catalog()
        (extracted / "covers").mkdir(exist_ok=True)
        (extracted / ".gitkeep").touch()
        _replace_directory(extracted, staged_catalog)
