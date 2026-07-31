from __future__ import annotations

import hashlib
import io
import json
import os
import subprocess
import tarfile
from datetime import UTC, datetime
from pathlib import Path

import pytest

from myebooks.catalog import build_catalog_artifact, index_library, install_catalog_archive
from myebooks.database import LibraryDatabase
from myebooks.demo import FakeDriveSource

PROJECT_DIR = Path(__file__).parents[1]


def test_catalog_artifact_contains_read_only_database_and_referenced_covers(settings, tmp_path):
    artifact = build_catalog_artifact(
        settings,
        FakeDriveSource(),
        output_dir=tmp_path / "dist",
        staged_catalog=tmp_path / "deploy" / "catalog",
        generated_at=datetime(2026, 7, 31, 12, 30, tzinfo=UTC),
    )

    assert artifact.version == "20260731T123000Z"
    assert artifact.book_count == 1
    assert artifact.cover_count == 1
    assert artifact.archive_path.is_file()
    assert artifact.checksum_path.is_file()
    assert (artifact.staged_catalog / "myebooks.sqlite3").is_file()
    assert len(list((artifact.staged_catalog / "covers").iterdir())) == 1

    with tarfile.open(artifact.archive_path, "r:gz") as archive:
        names = set(archive.getnames())
    assert "myebooks.sqlite3" in names
    assert "manifest.json" in names
    assert len([name for name in names if name.startswith("covers/")]) == 1
    assert not any(name.endswith((".epub", ".pdf")) for name in names)

    manifest = json.loads((artifact.staged_catalog / "manifest.json").read_text())
    assert manifest["book_count"] == 1
    assert manifest["source"] == "Drive de démonstration"
    deployed_database = LibraryDatabase(
        artifact.staged_catalog / "myebooks.sqlite3", read_only=True
    )
    deployed_database.validate_catalog()
    with pytest.raises(RuntimeError, match="lecture seule"):
        deployed_database.initialize()


def test_catalog_archive_can_be_verified_and_installed(settings, tmp_path):
    artifact = build_catalog_artifact(
        settings,
        FakeDriveSource(),
        output_dir=tmp_path / "dist",
        staged_catalog=tmp_path / "first" / "catalog",
    )
    installed = tmp_path / "second" / "catalog"

    install_catalog_archive(
        artifact.archive_path,
        artifact.checksum_path,
        staged_catalog=installed,
    )

    assert len(LibraryDatabase(installed / "myebooks.sqlite3", read_only=True).list_books()) == 1
    assert (installed / "manifest.json").is_file()
    assert len(list((installed / "covers").iterdir())) == 1


def test_empty_catalog_archive_installs_an_empty_covers_directory(settings, tmp_path):
    source = FakeDriveSource()
    source._files.clear()
    artifact = build_catalog_artifact(
        settings,
        source,
        output_dir=tmp_path / "dist",
        staged_catalog=tmp_path / "first" / "catalog",
    )
    installed = tmp_path / "second" / "catalog"

    install_catalog_archive(
        artifact.archive_path,
        artifact.checksum_path,
        staged_catalog=installed,
    )

    assert artifact.book_count == 0
    assert artifact.cover_count == 0
    assert (installed / "covers").is_dir()
    assert not any((installed / "covers").iterdir())


def test_catalog_artifact_can_reuse_existing_data_without_a_source(settings, tmp_path):
    index_library(settings, FakeDriveSource())

    artifact = build_catalog_artifact(
        settings,
        None,
        output_dir=tmp_path / "dist",
        staged_catalog=tmp_path / "deploy" / "catalog",
        skip_index=True,
    )

    manifest = json.loads((artifact.staged_catalog / "manifest.json").read_text())
    assert artifact.book_count == 1
    assert artifact.cover_count == 1
    assert artifact.result.indexed == 1
    assert manifest["source"] == "Cache local existant"


def test_reusing_existing_data_stops_an_indexation_in_progress(
    settings, tmp_path, monkeypatch
):
    database = LibraryDatabase(settings.database_path)
    database.initialize()
    sync_id = database.start_sync()

    def stop_index(_settings, requested_sync_id):
        assert requested_sync_id == sync_id
        database.fail_sync(sync_id, "Arrêt demandé par le test")

    monkeypatch.setattr("myebooks.catalog.request_index_cancellation", stop_index)
    artifact = build_catalog_artifact(
        settings,
        None,
        output_dir=tmp_path / "dist",
        staged_catalog=tmp_path / "deploy" / "catalog",
        skip_index=True,
    )

    assert artifact.book_count == 0
    assert database.latest_sync()["status"] == "failed"


def test_catalog_install_rejects_path_traversal(tmp_path):
    archive_path = tmp_path / "myebooks-catalog-unsafe.tar.gz"
    with tarfile.open(archive_path, "w:gz") as archive:
        content = b"unsafe"
        member = tarfile.TarInfo("../outside")
        member.size = len(content)
        archive.addfile(member, io.BytesIO(content))
    checksum_path = tmp_path / f"{archive_path.name}.sha256"
    checksum_path.write_text(
        f"{hashlib.sha256(archive_path.read_bytes()).hexdigest()}  {archive_path.name}\n"
    )

    with pytest.raises(ValueError, match="Chemin interdit"):
        install_catalog_archive(
            archive_path,
            checksum_path,
            staged_catalog=tmp_path / "deploy" / "catalog",
        )

    assert not (tmp_path / "outside").exists()


def test_catalog_scripts_are_executable_and_document_their_actions():
    for name in (
        "index_catalog",
        "build_catalog",
        "publish_catalog",
        "install_catalog",
        "build_scaleway_image",
    ):
        assert os.access(PROJECT_DIR / "scripts" / name, os.X_OK)

    result = subprocess.run(
        [str(PROJECT_DIR / "scripts" / "build_catalog"), "--help"],
        cwd=PROJECT_DIR,
        capture_output=True,
        check=False,
        text=True,
    )

    assert result.returncode == 0
    assert "génère l'artefact SQLite" in result.stdout
    assert "--drive-url" in result.stdout
    assert "--publish" in result.stdout
    assert "--skip-index" in result.stdout

    incompatible = subprocess.run(
        [
            str(PROJECT_DIR / "scripts" / "build_catalog"),
            "--skip-index",
            "--fake",
        ],
        cwd=PROJECT_DIR,
        capture_output=True,
        check=False,
        text=True,
    )
    assert incompatible.returncode == 2
    assert "ne peut pas être combiné" in incompatible.stderr

    image_help = subprocess.run(
        [str(PROJECT_DIR / "scripts" / "build_scaleway_image"), "--help"],
        cwd=PROJECT_DIR,
        capture_output=True,
        check=False,
        text=True,
    )
    assert image_help.returncode == 0
    assert "linux/amd64" in image_help.stdout
