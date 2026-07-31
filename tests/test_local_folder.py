from __future__ import annotations

from dataclasses import replace

import pytest

from myebooks.adapters.local_folder import LocalFolderSource
from myebooks.demo import demo_epub
from myebooks.domain import RemoteFile


def make_source(settings, library):
    return LocalFolderSource(
        replace(settings, source="local", local_library_dir=library)
    )


def test_local_folder_lists_recursively_and_reads_ebooks(settings, tmp_path):
    library = tmp_path / "ebooks"
    nested = library / "Romans"
    nested.mkdir(parents=True)
    content = demo_epub()
    (nested / "roman.epub").write_bytes(content)
    (library / "notes.txt").write_text("not an ebook")
    source = make_source(settings, library)

    files = source.list_files()

    assert len(files) == 1
    assert files[0].name == "roman.epub"
    assert files[0].mime_type == "application/epub+zip"
    assert "/" not in files[0].id
    assert source.download(files[0]) == content


def test_local_download_can_rebuild_its_safe_path_mapping(settings, tmp_path):
    library = tmp_path / "ebooks"
    library.mkdir()
    path = library / "book.pdf"
    path.write_bytes(b"pdf content")
    first_source = make_source(settings, library)
    remote_file = first_source.list_files()[0]

    fresh_source = make_source(settings, library)

    assert fresh_source.download(remote_file) == b"pdf content"


def test_local_folder_ignores_symbolic_links(settings, tmp_path):
    library = tmp_path / "ebooks"
    library.mkdir()
    outside = tmp_path / "outside.epub"
    outside.write_bytes(demo_epub())
    link = library / "linked.epub"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("Les liens symboliques ne sont pas disponibles sur cette plateforme")

    assert make_source(settings, library).list_files() == []


def test_local_download_rejects_unknown_identifier(settings, tmp_path):
    library = tmp_path / "ebooks"
    library.mkdir()
    source = make_source(settings, library)
    remote_file = RemoteFile(
        id="../outside",
        name="outside.epub",
        mime_type="application/epub+zip",
        modified_time="unknown",
    )

    with pytest.raises(ValueError, match="Identifiant de fichier local invalide"):
        source.download(remote_file)
