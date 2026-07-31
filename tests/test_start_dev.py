from __future__ import annotations

import os
import subprocess
from pathlib import Path

PROJECT_DIR = Path(__file__).parents[1]
START_DEV = PROJECT_DIR / "start_dev"
START_DEV_IMPLEMENTATION = PROJECT_DIR / "scripts" / "start_dev"


def run_start_dev(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(START_DEV), *arguments],
        cwd=PROJECT_DIR,
        capture_output=True,
        check=False,
        text=True,
    )


def test_start_dev_is_executable_and_documents_options():
    assert os.access(START_DEV, os.X_OK)

    result = run_start_dev("--help")

    assert result.returncode == 0
    assert "Usage: ./start_dev" in result.stdout
    assert "--library" in result.stdout
    assert "--drive-url" in result.stdout
    assert "--kobo" in result.stdout
    assert "--force-index" in result.stdout
    assert "/kobo" in START_DEV_IMPLEMENTATION.read_text()
    assert "EBOOK_BACKGROUND_INDEX=1" in START_DEV_IMPLEMENTATION.read_text()
    assert "pandaIndexKobo" not in START_DEV_IMPLEMENTATION.read_text()
    assert "./start_dev --kobo" in result.stdout


def test_start_dev_rejects_invalid_port():
    result = run_start_dev("--port", "invalid")

    assert result.returncode == 2
    assert "le port doit être un entier" in result.stderr


def test_start_dev_rejects_missing_library(tmp_path):
    result = run_start_dev("--library", str(tmp_path / "missing"))

    assert result.returncode == 1
    assert "n'est pas lisible" in result.stderr


def test_start_dev_rejects_non_google_drive_url():
    result = run_start_dev(
        "--drive-url",
        "https://evil.example/drive/folders/1AbCdEfGhIjKlMnOpQrStUvWx",
    )

    assert result.returncode == 2
    assert "URL HTTPS de dossier drive.google.com" in result.stderr


def test_start_dev_rejects_conflicting_sources(tmp_path):
    result = run_start_dev(
        "--library",
        str(tmp_path),
        "--drive-url",
        "https://drive.google.com/drive/folders/1AbCdEfGhIjKlMnOpQrStUvWx",
    )

    assert result.returncode == 2
    assert "ne peuvent pas être utilisés ensemble" in result.stderr
