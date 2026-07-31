from __future__ import annotations

import pytest

from myebooks.config import Settings


@pytest.fixture
def settings(tmp_path):
    return Settings(
        data_dir=tmp_path / "data",
        source="fake",
        max_file_size=10 * 1024 * 1024,
        max_epub_expanded_size=20 * 1024 * 1024,
        max_epub_entries=100,
    )
